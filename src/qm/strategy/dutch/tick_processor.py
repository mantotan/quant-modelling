"""Shared tick processing — identical in live and backtest.

Extracted from monitor_pulse.py and dutch_backtest.py to ensure both systems
use the exact same code paths for inference and order processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from datetime import datetime

from qm.core.types import PartialBar
from qm.features.live_cache import CrossAssetLiveFeatureCache


def run_inference(
    model,
    calibrator,
    feat_cache,
    partial: PartialBar,
    elapsed_pct: float,
    btc_partial: PartialBar | None = None,
) -> tuple[float, float, np.ndarray]:
    """Compute features → raw_prob → cal_prob.

    Returns (raw_prob, cal_prob, features).
    """
    if btc_partial is not None and isinstance(feat_cache, CrossAssetLiveFeatureCache):
        feat_cache.set_btc_partial(btc_partial)

    features = feat_cache.get_features(partial)
    raw_prob = float(model.predict(features.reshape(1, -1))[0])

    cal_prob = raw_prob
    if calibrator:
        cal_prob = float(
            calibrator.transform(
                np.array([raw_prob]),
                np.array([elapsed_pct]),
            )[0]
        )

    return raw_prob, cal_prob, features


def process_tick(
    time_pct: float,
    cal_prob: float,
    book_up,
    book_dn,
    engine,
    sim,
    now: datetime | None = None,
) -> tuple[list, list]:
    """Run engine + simulator for one tick.

    Returns (orders, fills).
    """
    orders = engine.on_tick(time_pct, cal_prob, book_up, book_dn)

    # V7.5: Cancel pending orders on flip kill
    if engine.flip_killed and not orders:
        for c_order in sim.cancel_all():
            engine.on_order_cancelled(c_order)

    for order in orders:
        sim.place(order)

    fills = sim.on_tick(time_pct, book_up, book_dn, now=now)
    for fill in fills:
        engine.on_fill(fill.order, fill.fill_price, fill.filled_shares)

    return orders, fills
