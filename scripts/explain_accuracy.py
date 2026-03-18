"""Explain exactly how accuracy is calculated -- step by step with examples."""

import sys
sys.path.insert(0, "src")
import numpy as np
from pathlib import Path
from qm.core.types import Asset, Timeframe
from qm.data.storage.parquet import ParquetStore
from qm.features.pipeline import FeaturePipeline
from qm.model.targets.binary import BinaryDirectionTarget
import lightgbm as lgb

store = ParquetStore(base_dir=Path("data/raw/ohlcv"))
bars = store.read_bars(Asset.BTC, Timeframe.M5)

# Show raw data
print("=== RAW DATA (first 5 bars) ===")
print(f"{'Time':<25}  {'Open':>10}  {'Close':>10}  {'NextOpen':>10}  {'NextClose':>10}  {'NextBarUp':>10}")
for i in range(5):
    next_up = "UP" if bars["close"][i+1] >= bars["open"][i+1] else "DOWN"
    print(f"{str(bars['time'][i]):<25}  {bars['open'][i]:>10.2f}  {bars['close'][i]:>10.2f}  "
          f"{bars['open'][i+1]:>10.2f}  {bars['close'][i+1]:>10.2f}  {next_up:>10}")

print()
print("=== TARGET DEFINITION ===")
print("Target = 1 if close[t+1] >= open[t+1]  (did the NEXT bar go up?)")
print("This matches Polymarket: 'Up if price at END of window >= START of window'")
print()

# Target stats
target = BinaryDirectionTarget(horizon_bars=1).compute(bars)
valid = target.drop_nulls()
print(f"Total bars:      {len(bars):,}")
print(f"Base rate:       {valid.mean():.4f} ({valid.mean()*100:.2f}% of bars went Up)")
print(f"  Up bars:       {int(valid.sum()):,}")
print(f"  Down bars:     {len(valid) - int(valid.sum()):,}")
print()

# Features and model
print("=== WHAT THE MODEL SEES (features at time t) ===")
print("At time t, the model has ONLY past information:")
print("  - RSI(14): average of gains vs losses over last 14 bars")
print("  - Stochastic K: where close is relative to 14-bar high/low range")
print("  - MACD: difference between 12-bar and 26-bar exponential moving averages")
print("  - Volume ratio: current volume vs 10-bar average")
print("  - etc. (11 selected features total)")
print()
print("The model DOES NOT see open[t+1] or close[t+1] -- those are in the future.")
print()

# Load model and predict
pipeline = FeaturePipeline()
featured = pipeline.compute(bars)
target = BinaryDirectionTarget(horizon_bars=1).compute(featured)
featured = featured.with_columns(target)
feature_names = [f for f in pipeline.feature_names if f not in {"return_1", "log_return_1", "gap"}]
lookback = pipeline.max_lookback
clean = featured.slice(lookback).drop_nulls(subset=["target"])

split = int(len(clean) * 0.80)
X_test = clean.slice(split).select(feature_names).fill_null(0).to_numpy().astype(np.float64)
y_test = clean.slice(split)["target"].to_numpy().astype(np.float64)

model = lgb.Booster(model_file="data/models/BTC_5m_v3/model.txt")

# Model uses only selected features -- need to match
selected = model.feature_name()
X_test_sel = clean.slice(split).select(selected).fill_null(0).to_numpy().astype(np.float64)
preds = model.predict(X_test_sel)

print("=== HOW ACCURACY IS CALCULATED ===")
print()
print("Step 1: Model outputs P(Up) -- a probability between 0 and 1")
print("Step 2: If P(Up) > 0.5 -> predict Up, else predict Down")
print("Step 3: Compare prediction to actual outcome")
print("Step 4: Accuracy = correct / total")
print()

# Examples
print("=== FIRST 15 PREDICTIONS ===")
print(f"{'#':>4}  {'P(Up)':>7}  {'Predict':>8}  {'Actual':>8}  {'Result':>8}")
print("-" * 45)
for i in range(15):
    pred_label = "Up" if preds[i] > 0.5 else "Down"
    actual_label = "Up" if y_test[i] == 1 else "Down"
    correct = "OK" if (preds[i] > 0.5) == (y_test[i] == 1) else "WRONG"
    print(f"{i:>4}  {preds[i]:>7.4f}  {pred_label:>8}  {actual_label:>8}  {correct:>8}")

print()
acc = float(np.mean((preds > 0.5) == (y_test == 1)))
always_up = float(y_test.mean())
always_down = 1 - always_up
best_naive = max(always_up, always_down)

print("=== ACCURACY COMPARISON ===")
print(f"Always predict Up:     {always_up:.4f} ({always_up*100:.2f}%)")
print(f"Always predict Down:   {always_down:.4f} ({always_down*100:.2f}%)")
print(f"Best naive baseline:   {best_naive:.4f} ({best_naive*100:.2f}%)")
print(f"Our model:             {acc:.4f} ({acc*100:.2f}%)")
print(f"Lift over naive:       {acc - best_naive:+.4f} ({(acc - best_naive)*100:+.2f}%)")
print()

# Confidence analysis
print("=== MODEL CONFIDENCE DISTRIBUTION ===")
print(f"Mean P(Up): {preds.mean():.4f}")
print(f"Std P(Up):  {preds.std():.4f}")
print(f"Min P(Up):  {preds.min():.4f}")
print(f"Max P(Up):  {preds.max():.4f}")
print()
for lo, hi, label in [
    (0.00, 0.45, "Strong Down"),
    (0.45, 0.48, "Moderate Down"),
    (0.48, 0.50, "Weak Down"),
    (0.50, 0.52, "Weak Up"),
    (0.52, 0.55, "Moderate Up"),
    (0.55, 1.00, "Strong Up"),
]:
    mask = (preds >= lo) & (preds < hi)
    n = mask.sum()
    if n > 0:
        actual_up_rate = float(y_test[mask].mean())
        print(f"  {label:<15} P(Up) [{lo:.2f}-{hi:.2f}): "
              f"n={n:>6} ({n/len(preds)*100:>5.1f}%), actual Up={actual_up_rate:.4f}")

print()
print("=== KEY QUESTION ===")
print("Is the model actually predicting the future, or is there still bias?")
print()
print("Sanity checks:")

# Check: does shuffling features kill accuracy?
rng = np.random.RandomState(99)
X_shuffled = X_test_sel.copy()
for col in range(X_shuffled.shape[1]):
    rng.shuffle(X_shuffled[:, col])
preds_shuffled = model.predict(X_shuffled)
acc_shuffled = float(np.mean((preds_shuffled > 0.5) == (y_test == 1)))
print(f"  Shuffled features accuracy: {acc_shuffled:.4f} (should be ~{best_naive:.4f})")

# Check: does the model just predict the majority class?
pct_pred_up = (preds > 0.5).mean()
print(f"  Model predicts Up: {pct_pred_up*100:.1f}% of the time (base rate: {always_up*100:.1f}%)")
