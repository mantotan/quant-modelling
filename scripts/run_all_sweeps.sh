#!/bin/bash
# Run parameter sweeps for all 11 remaining pairs (BTC_15m already done)
set -e
PAIRS="ETH_5m ETH_15m ETH_1h BTC_5m BTC_1h SOL_5m SOL_15m SOL_1h XRP_5m XRP_15m XRP_1h"
for pair in $PAIRS; do
    echo "=== Starting sweep for $pair ==="
    uv run scripts/dutch_param_sweep.py --pair $pair --output data/sweep_${pair}.tsv 2>&1 | grep -E "SWEEP|TOP 10|^$|Precomputed|experiments completed|^\s+#" 
    echo "=== Completed $pair ==="
    echo
done
echo "ALL SWEEPS COMPLETE"
