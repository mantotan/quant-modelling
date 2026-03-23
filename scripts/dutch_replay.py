"""Replay a single bar from live tick log through the backtest pipeline.

Reads enriched tick JSONL from live paper trading and replays the exact
same price/book stream through BarBuilder + model + engine, comparing
every prediction and order against what live produced.

Usage:
    uv run scripts/dutch_replay.py --pair BTC_5m --bar-id 1774262700
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from qm.core.types import Asset, Timeframe  # noqa: E402
from qm.data.connectors.polymarket_ws import TokenBook  # noqa: E402
from qm.data.ingestion.bar_builder import BarBuilder  # noqa: E402
from qm.features.live_cache import CrossAssetLiveFeatureCache, LiveFeatureCache  # noqa: E402
from qm.features.pipeline import FeaturePipeline  # noqa: E402
from qm.model.calibration.calibrator import TimeAwareCalibrator  # noqa: E402
from qm.strategy.dutch.engine import DutchAccumulationEngine, DutchConfig  # noqa: E402
from qm.strategy.dutch.fill_simulator import LimitOrderSimulator  # noqa: E402
from qm.strategy.dutch.tick_processor import process_tick, run_inference  # noqa: E402

logger = logging.getLogger(__name__)

ASSET_MAP = {"BTC": Asset.BTC, "ETH": Asset.ETH, "SOL": Asset.SOL, "XRP": Asset.XRP}
TF_MAP = {"5m": Timeframe.M5, "15m": Timeframe.M15, "1h": Timeframe.H1}
BAR_SECONDS = {"5m": 300.0, "15m": 900.0, "1h": 3600.0}


def load_live_ticks(pair_dir: Path, date_str: str, bar_id: int) -> list[dict]:
    """Load enriched ticks for a specific bar from live tick log."""
    tick_file = pair_dir / f"ticks_{date_str}.jsonl"
    if not tick_file.exists():
        raise FileNotFoundError(f"No tick file: {tick_file}")

    ticks = []
    for line in open(tick_file):
        t = json.loads(line)
        if t["bar_id"] == bar_id and t.get("spot_price") is not None:
            ticks.append(t)
    return ticks


def load_live_bar(pair_dir: Path, date_str: str, bar_id: int) -> dict | None:
    """Load the live bar result for comparison."""
    bar_file = pair_dir / f"bars_{date_str}.jsonl"
    if not bar_file.exists():
        return None
    for line in open(bar_file):
        b = json.loads(line)
        if b.get("bar_id") == bar_id:
            return b
    return None


def warm_up_cache(feat_cache, asset_enum, tf_enum):
    """Warm up feature cache from historical OHLCV (same as backtest/live)."""
    from qm.data.storage.parquet import ParquetStore

    store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
    bars_df = store.read_bars(asset_enum, tf_enum)
    if bars_df.is_empty():
        return
    pipeline = FeaturePipeline()
    n = min(500, len(bars_df))
    featured = pipeline.compute(bars_df.tail(n))
    last_row = featured.row(-1, named=True)
    cache_dict = {
        name: float(val)
        for name in pipeline.feature_names
        if (val := last_row.get(name)) is not None
    }
    feat_cache.update_history(cache_dict)
    logger.info("Warm-up: cached %d features from %d bars", len(cache_dict), n)


def replay_bar(
    asset: str,
    tf_label: str,
    bar_id: int,
    ticks: list[dict],
    live_bar: dict | None,
) -> dict:
    """Replay one bar through the backtest pipeline using live's exact inputs."""
    asset_enum = ASSET_MAP[asset]
    tf_enum = TF_MAP[tf_label]
    bar_secs = BAR_SECONDS[tf_label]

    # Load model + calibrator
    model_dir = Path("data/models/pulse_v2") / f"{asset}_{tf_label}"
    import lightgbm as lgb
    model = lgb.Booster(model_file=str(model_dir / "model.lgb"))
    cal_path = model_dir / "calibrator.json"
    calibrator = TimeAwareCalibrator.load(cal_path) if cal_path.exists() else None

    # Feature cache
    cache_dir = model_dir
    if (model_dir / "model_btc.lgb").exists() or asset != "BTC":
        feat_cache = CrossAssetLiveFeatureCache.from_model_dir(
            cache_dir, asset=asset_enum, timeframe=tf_enum,
        )
    else:
        feat_cache = LiveFeatureCache.from_model_dir(
            cache_dir, asset=asset_enum, timeframe=tf_enum,
        )
    warm_up_cache(feat_cache, asset_enum, tf_enum)

    # BarBuilder
    bar_builder = BarBuilder(assets=[asset_enum], timeframes=[tf_enum])

    # Engine + Simulator
    knobs_path = Path(f"autoresearch/dutch/knobs_{asset}_{tf_label}.json")
    if knobs_path.exists():
        with open(knobs_path) as f:
            knobs = json.load(f)
        sim_knobs = knobs.pop("fill_simulator", {})
    else:
        knobs = {}
        sim_knobs = {}

    config = DutchConfig(**{k: v for k, v in knobs.items()
                           if k in DutchConfig.__dataclass_fields__ and not k.startswith("_")})
    engine = DutchAccumulationEngine(config)
    sim = LimitOrderSimulator(**sim_knobs)

    # Window times
    window_start = datetime.fromtimestamp(bar_id, tz=UTC)
    window_end = window_start + timedelta(seconds=bar_secs)

    engine.reset()
    sim.reset()
    engine.set_bar_info(
        bar_id=bar_id,
        condition_id="replay",
        window_start=str(bar_id),
        window_end=str(bar_id + int(bar_secs)),
    )

    # Replay ticks
    cal_prob = 0.5
    last_spot = None
    last_inference_pct = -1.0
    replay_inferences = []
    replay_orders = []

    for tick in ticks:
        time_pct = tick["time_pct"]
        spot = tick["spot_price"]

        # Only feed BarBuilder when spot_price changes (same as live)
        if spot != last_spot and spot is not None:
            last_spot = spot
            ts = window_start + timedelta(seconds=time_pct * bar_secs)
            bar_builder.on_trade(asset_enum, spot, 0.001, ts)

        # Get partial and elapsed_pct
        ts = window_start + timedelta(seconds=time_pct * bar_secs)
        partial = bar_builder.get_partial_bar(asset_enum, tf_enum, now=ts)
        if partial is None:
            continue

        current_elapsed_pct = partial.elapsed_seconds / (
            partial.remaining_seconds + partial.elapsed_seconds + 1e-10
        )

        # Inference: only when live actually inferred (is_inference flag)
        # Fallback for old logs without is_inference: detect cal_prob changes
        live_cal = tick["cal_prob"]
        did_infer = tick.get("is_inference", False)
        if not did_infer:
            # Fallback: infer when cal_prob changed (old tick logs)
            did_infer = (live_cal != cal_prob or last_inference_pct < 0)

        if did_infer:
            _raw, replay_cal, _feats = run_inference(
                model, calibrator, feat_cache,
                partial, current_elapsed_pct, None,
            )
            replay_inferences.append({
                "time_pct": time_pct,
                "elapsed_pct": round(current_elapsed_pct, 6),
                "live_cal": live_cal,
                "replay_cal": round(replay_cal, 4),
                "live_raw": tick.get("raw_prob"),
                "replay_raw": round(_raw, 4),
                "delta_cal": round(abs(replay_cal - live_cal), 6),
                "delta_raw": round(abs(_raw - (tick.get("raw_prob") or 0)), 6),
            })
            cal_prob = replay_cal
            last_inference_pct = time_pct

        # Build books from tick BBO
        if tick.get("bid_up") is not None:
            book_up = TokenBook(token_id="replay_up")
            book_up.best_bid = tick["bid_up"]
            book_up.best_ask = tick["ask_up"]
            book_up.bids = {tick["bid_up"]: 100.0}
            book_up.asks = {tick["ask_up"]: 100.0}

            book_dn = TokenBook(token_id="replay_dn")
            book_dn.best_bid = tick["bid_dn"]
            book_dn.best_ask = tick["ask_dn"]
            book_dn.bids = {tick["bid_dn"]: 100.0}
            book_dn.asks = {tick["ask_dn"]: 100.0}
        else:
            book_up = book_dn = None

        orders, fills = process_tick(
            current_elapsed_pct, cal_prob, book_up, book_dn, engine, sim,
        )
        for o in orders:
            replay_orders.append({
                "side": o.side,
                "limit_price": o.limit_price,
                "shares": round(o.shares, 2),
                "time_pct": round(o.time_pct, 4),
            })

    # Resolve
    if live_bar:
        outcome = live_bar["outcome"]
    else:
        outcome = "UP"  # fallback

    sim.cancel_all()
    summary = engine.resolve(outcome)

    # Compare
    live_orders = live_bar.get("orders", []) if live_bar else []
    live_flips = live_bar["model_stats"]["flips"] if live_bar else 0
    replay_flips = engine._model_flips if hasattr(engine, "_model_flips") else 0

    return {
        "bar_id": bar_id,
        "outcome": outcome,
        "inferences": replay_inferences,
        "replay_orders": replay_orders,
        "live_orders": live_orders,
        "replay_pnl": summary.pnl.get("profit", 0) if summary.pnl else 0,
        "live_pnl": live_bar["pnl"]["profit"] if live_bar else 0,
        "replay_cost": summary.cost.get("total", 0) if summary.cost else 0,
        "live_cost": live_bar["cost"]["total"] if live_bar else 0,
        "replay_flips": replay_flips,
        "live_flips": live_flips,
    }


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    p = argparse.ArgumentParser(description="Replay live bar through backtest pipeline")
    p.add_argument("--pair", required=True, help="e.g. BTC_5m")
    p.add_argument("--bar-id", type=int, required=True, help="Bar ID (Unix timestamp)")
    p.add_argument("--date", default=None, help="Date (YYYY-MM-DD), auto-detected if omitted")
    args = p.parse_args()

    asset, tf_label = args.pair.split("_")
    pair_dir = Path(f"data/dutch_paper/{asset}_{tf_label}")

    date_str = args.date or datetime.fromtimestamp(args.bar_id, tz=UTC).strftime("%Y-%m-%d")

    ticks = load_live_ticks(pair_dir, date_str, args.bar_id)
    if not ticks:
        print(f"No enriched ticks for bar {args.bar_id}")
        return

    live_bar = load_live_bar(pair_dir, date_str, args.bar_id)

    print(f"Replaying bar {args.bar_id} ({asset}/{tf_label})")
    print(f"  Live ticks: {len(ticks)}")
    print(f"  Live bar: {'found' if live_bar else 'missing'}")
    print()

    result = replay_bar(asset, tf_label, args.bar_id, ticks, live_bar)

    # Print inference comparison
    infs = result["inferences"]
    print(f"Inferences: {len(infs)}")
    exact = sum(1 for i in infs if i["delta_cal"] < 0.001)
    close = sum(1 for i in infs if i["delta_cal"] < 0.01)
    print(f"  cal_prob exact (<0.001): {exact}/{len(infs)} ({exact/len(infs)*100:.0f}%)")
    print(f"  cal_prob close (<0.01):  {close}/{len(infs)} ({close/len(infs)*100:.0f}%)")
    if infs:
        worst = max(infs, key=lambda x: x["delta_cal"])
        print(f"  Worst delta: {worst['delta_cal']:.4f} at t={worst['time_pct']:.4f} "
              f"(replay={worst['replay_cal']:.4f} live={worst['live_cal']:.4f})")

    # Print order comparison
    ro = result["replay_orders"]
    lo = result["live_orders"]
    print(f"\nOrders: replay={len(ro)} live={len(lo)}")
    for i, (r, l) in enumerate(zip(ro, lo)):
        side_ok = r["side"] == l["side"]
        price_ok = abs(r["limit_price"] - l["limit_price"]) < 0.02
        print(f"  [{i}] side: R={r['side']} L={l['side']} {'OK' if side_ok else 'DIFF'} | "
              f"price: R={r['limit_price']} L={l['limit_price']} {'OK' if price_ok else 'DIFF'} | "
              f"t: R={r['time_pct']:.4f} L={l['time_pct']:.4f}")

    # Print summary
    print(f"\nFlips:  replay={result['replay_flips']}  live={result['live_flips']}  "
          f"delta={abs(result['replay_flips']-result['live_flips'])}")
    print(f"Cost:   replay=${result['replay_cost']:.2f}  live=${result['live_cost']:.2f}")
    print(f"PnL:    replay=${result['replay_pnl']:.2f}  live=${result['live_pnl']:.2f}")

    # Verdict
    all_ok = (
        len(ro) == len(lo)
        and all(r["side"] == l["side"] for r, l in zip(ro, lo))
        and abs(result["replay_flips"] - result["live_flips"]) <= 1
        and exact / len(infs) > 0.95 if infs else True
    )
    print(f"\nVerdict: {'PASS' if all_ok else 'FAIL'}")


if __name__ == "__main__":
    main()
