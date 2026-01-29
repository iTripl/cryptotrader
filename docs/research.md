# 2025 Strategy Research (BTC/ETH)

## Trend-following (Donchian ensemble)
**Source:** “Catching Crypto Trends; A Tactical Approach for Bitcoin and Altcoins” (Zarattini, Pagani, Barbon, 2025)

Highlights:
- Uses a Donchian channel trend model with **multiple lookback windows**.
- Ensemble vote across windows is used to form a single signal.
- Evidence of strong risk-adjusted returns in crypto when trend signals are used.

Implementation: `strategies/donchian_trend.py`

## Cross-sectional momentum
**Source:** “Cross-sectional Momentum in Cryptocurrency Markets” (Drogen, Hoffstein, Otte, 2023)

Highlights:
- Assets that outperform over **~30 days** tend to continue to outperform over the next **~7 days**.
- Strategy selects top performers over the lookback window.

Implementation: `strategies/cross_section_momentum.py`

## Notes
- These are simplified, infrastructure-grade implementations to test signals.
- Use the config sections in `config/config.ini` to tune parameters.
