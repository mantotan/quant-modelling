# Audit Report
Updated: 2026-03-19T15:35:00Z
After: Alpha feature activation

## Verdict: CONTINUE
Alpha features (funding rates) are now active. New baseline needed. Previous 21 iterations archived. The knobs-only search space was exhausted — alpha features open a new frontier.

## Progress
- Pre-alpha: 21 iterations, Brier 0.2055→0.1439 (-30%), all acceptance criteria met
- Alpha activation: 25,337 funding rate records downloaded (4 assets, 2020-2026)
- Dataset regenerated with 50 features (previously 23)

## Acceptance Status (pre-alpha best, carried forward)
| Metric | Target | BTC Best | ETH Best |
|--------|--------|----------|----------|
| Brier | < 0.25 | 0.1439 | 0.1966 |
| ECE | < 0.05 | 0.0041 | 0.0216 |
| PnL | > 0 | $67.26 | $309.08 |
| Max DD | < 30% | 28.7% | 5.25% |

## Next Audit
After 20 iterations on the alpha-enriched model.
