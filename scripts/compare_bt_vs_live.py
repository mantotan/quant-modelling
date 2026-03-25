"""Apple-to-apple comparison: backtest vs live paper trading on same bars."""
import json
from pathlib import Path


def load_bars(base_dir, pair):
    bars = []
    asset, tf = pair.split("_")
    d = Path(base_dir) / f"{asset}_{tf}"
    if not d.exists():
        d = Path(base_dir) / pair
    for bf in sorted(d.glob("bars_*.jsonl")):
        with open(bf) as f:
            for line in f:
                if line.strip():
                    bars.append(json.loads(line.strip()))
    return bars


def get_buy_side(bar):
    for o in bar.get("orders", []):
        # Orders use "side" field (UP/DN), not "action"/"contract"
        return o.get("side", "?")
    return None


def main():
    pairs = [
        "BTC_5m", "BTC_15m", "BTC_1h",
        "ETH_5m", "ETH_15m", "ETH_1h",
        "SOL_5m", "SOL_15m", "SOL_1h",
        "XRP_5m", "XRP_15m", "XRP_1h",
    ]

    print("=" * 160)
    print("  APPLE-TO-APPLE: Same bars, same config — Backtest vs Live")
    print("=" * 160)

    # Accumulators
    g = dict(
        overlap=0, bt_pnl=0, lv_pnl=0,
        same=0, diff=0, both_zero=0, bt_only=0, lv_only=0,
        ss_bt=0, ss_lv=0, ds_bt=0, ds_lv=0,
        flip_diffs=[],
    )
    rows = []

    for pair in pairs:
        live_bars = load_bars("data/dutch_paper", pair)
        bt_bars = load_bars("data/dutch_backtest", pair)
        if not live_bars:
            continue

        live_by_id = {b["bar_id"]: b for b in live_bars if b.get("bar_id")}
        bt_by_id = {b["bar_id"]: b for b in bt_bars if b.get("bar_id")}
        common = sorted(set(live_by_id) & set(bt_by_id))
        if not common:
            continue

        same = diff = both_zero = bt_only = lv_only = 0
        bt_pnl = lv_pnl = 0
        bt_w = bt_l = lv_w = lv_l = 0

        for bid in common:
            bt = bt_by_id[bid]
            lv = live_by_id[bid]
            btp = bt["pnl"]["profit"]
            lvp = lv["pnl"]["profit"]
            btc = bt["cost"]["total"]
            lvc = lv["cost"]["total"]
            bt_pnl += btp
            lv_pnl += lvp
            if btp > 0: bt_w += 1
            if btp < 0: bt_l += 1
            if lvp > 0: lv_w += 1
            if lvp < 0: lv_l += 1

            # Flip divergence
            bf = bt.get("model_stats", {}).get("flips", 0)
            lf = lv.get("model_stats", {}).get("flips", 0)
            g["flip_diffs"].append(abs(bf - lf))

            # Side classification
            if btc == 0 and lvc == 0:
                both_zero += 1
            elif btc == 0 and lvc > 0:
                lv_only += 1
            elif btc > 0 and lvc == 0:
                bt_only += 1
            else:
                bs = get_buy_side(bt)
                ls = get_buy_side(lv)
                if bs and ls:
                    if bs == ls:
                        same += 1
                        g["ss_bt"] += btp
                        g["ss_lv"] += lvp
                    else:
                        diff += 1
                        g["ds_bt"] += btp
                        g["ds_lv"] += lvp

        bt_wr = bt_w / (bt_w + bt_l) * 100 if bt_w + bt_l else 0
        lv_wr = lv_w / (lv_w + lv_l) * 100 if lv_w + lv_l else 0
        total_active = same + diff
        agree = same / total_active * 100 if total_active else 0

        g["overlap"] += len(common)
        g["bt_pnl"] += bt_pnl
        g["lv_pnl"] += lv_pnl
        g["same"] += same
        g["diff"] += diff
        g["both_zero"] += both_zero
        g["bt_only"] += bt_only
        g["lv_only"] += lv_only

        rows.append((pair, len(common), bt_pnl, lv_pnl, bt_wr, lv_wr,
                      same, diff, both_zero, bt_only, lv_only, agree))

    # Summary table
    hdr = (f"  {'Pair':<12} {'Bars':>5} {'BT_PnL':>9} {'LV_PnL':>9} {'Gap':>9} "
           f"{'BT_WR':>6} {'LV_WR':>6} {'Same':>5} {'Diff':>5} "
           f"{'BothZ':>6} {'BT_only':>8} {'LV_only':>8} {'Agree%':>7}")
    print(hdr)
    print("  " + "-" * 130)

    for r in rows:
        pair, n, btp, lvp, btwr, lvwr, ss, ds, bz, bo, lo, ag = r
        gap = lvp - btp
        print(f"  {pair:<12} {n:>5} ${btp:>8.2f} ${lvp:>8.2f} ${gap:>+8.2f} "
              f"{btwr:>5.1f}% {lvwr:>5.1f}% {ss:>5} {ds:>5} "
              f"{bz:>6} {bo:>8} {lo:>8} {ag:>6.0f}%")

    print("  " + "-" * 130)
    ta = g["same"] + g["diff"]
    ga = g["same"] / ta * 100 if ta else 0
    print(f"  {'TOTAL':<12} {g['overlap']:>5} ${g['bt_pnl']:>8.2f} ${g['lv_pnl']:>8.2f} "
          f"${g['lv_pnl']-g['bt_pnl']:>+8.2f} {'':>6} {'':>6} {g['same']:>5} {g['diff']:>5} "
          f"{g['both_zero']:>6} {g['bt_only']:>8} {g['lv_only']:>8} {ga:>6.0f}%")

    # Divergence analysis
    print("\n" + "=" * 160)
    print("  DIVERGENCE ANALYSIS")
    print("=" * 160)

    print(f"\n  SIDE AGREEMENT (when both BT and LV traded same bar):")
    print(f"    Same side (agreed):     {g['same']:>4} bars ({ga:.0f}%)")
    print(f"    OPPOSITE side (disagree): {g['diff']:>4} bars ({100-ga:.0f}%)")

    print(f"\n  ACTIVITY DIVERGENCE (one traded, other skipped):")
    print(f"    Both skipped:           {g['both_zero']:>4} bars")
    print(f"    BT traded, LV skipped:  {g['bt_only']:>4} bars")
    print(f"    LV traded, BT skipped:  {g['lv_only']:>4} bars")

    print(f"\n  PnL BY SIDE AGREEMENT:")
    print(f"    Same side bars:     BT=${g['ss_bt']:>+9.2f}  LV=${g['ss_lv']:>+9.2f}  gap=${g['ss_lv']-g['ss_bt']:>+9.2f}")
    print(f"    Opposite side bars: BT=${g['ds_bt']:>+9.2f}  LV=${g['ds_lv']:>+9.2f}  gap=${g['ds_lv']-g['ds_bt']:>+9.2f}")

    # Flip analysis
    fd = g["flip_diffs"]
    if fd:
        print(f"\n  MODEL FLIP DIVERGENCE (same bar, BT vs LV flip count):")
        print(f"    Avg flip count difference: {sum(fd)/len(fd):.1f}")
        exact = sum(1 for d in fd if d == 0)
        w1 = sum(1 for d in fd if d <= 1)
        w2 = sum(1 for d in fd if d <= 2)
        big = sum(1 for d in fd if d >= 5)
        print(f"    Exact match (0 diff):     {exact:>4}/{len(fd)} ({exact/len(fd)*100:.0f}%)")
        print(f"    Within 1 flip:            {w1:>4}/{len(fd)} ({w1/len(fd)*100:.0f}%)")
        print(f"    Within 2 flips:           {w2:>4}/{len(fd)} ({w2/len(fd)*100:.0f}%)")
        print(f"    Big divergence (>=5):     {big:>4}/{len(fd)} ({big/len(fd)*100:.0f}%)")

    # Impact quantification
    print(f"\n  IMPACT QUANTIFICATION:")

    # What if live had BT's predictions on disagreement bars?
    counterfactual = g["lv_pnl"] - g["ds_lv"] + g["ds_bt"]
    print(f"    Actual live PnL:         ${g['lv_pnl']:>+9.2f}")
    print(f"    If LV had BT predictions on disagreement bars: ${counterfactual:>+9.2f}")
    print(f"    Prediction divergence cost:  ${g['ds_lv'] - g['ds_bt']:>+9.2f}")

    # What fraction of the total gap is from disagreement?
    total_gap = g["lv_pnl"] - g["bt_pnl"]
    disagree_gap = g["ds_lv"] - g["ds_bt"]
    agree_gap = g["ss_lv"] - g["ss_bt"]
    print(f"\n    Total BT-to-Live gap:     ${total_gap:>+9.2f}")
    print(f"    From opposite-side bars:  ${disagree_gap:>+9.2f} ({abs(disagree_gap/total_gap)*100 if total_gap else 0:.0f}% of gap)")
    print(f"    From same-side bars:      ${agree_gap:>+9.2f} ({abs(agree_gap/total_gap)*100 if total_gap else 0:.0f}% of gap)")
    skip_gap = total_gap - disagree_gap - agree_gap
    print(f"    From skip divergence:     ${skip_gap:>+9.2f} ({abs(skip_gap/total_gap)*100 if total_gap else 0:.0f}% of gap)")


if __name__ == "__main__":
    main()
