from data.schemas import Candle
from strategies.atr_breakout import AtrBreakoutStrategy
from strategies.liquidity_reversal import LiquidityReversalStrategy
from strategies.tsmom import TimeSeriesMomentumStrategy


def _candle(
    ts: int,
    close: float,
    high: float | None = None,
    low: float | None = None,
    volume: float = 100.0,
    symbol: str = "BTCUSDT",
    timeframe: str = "1m",
) -> Candle:
    return Candle(
        timestamp=ts,
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
        symbol=symbol,
        timeframe=timeframe,
        exchange="bybit",
    )


def test_tsmom_emits_on_threshold() -> None:
    strategy = TimeSeriesMomentumStrategy(
        None,
        {
            "lookback_bars": "3",
            "min_momentum": "0.01",
            "allow_short": "true",
            "confidence": "0.7",
            "horizon": "5m",
            "volatility_regime": "normal",
        },
    )

    assert list(strategy.on_candle(_candle(1, 100.0))) == []
    assert list(strategy.on_candle(_candle(2, 102.0))) == []
    assert list(strategy.on_candle(_candle(3, 104.0))) == []
    signals = list(strategy.on_candle(_candle(4, 106.0)))
    assert len(signals) == 1
    assert signals[0].direction == "LONG"
    assert list(strategy.on_candle(_candle(5, 108.0))) == []


def test_atr_breakout_triggers_long() -> None:
    strategy = AtrBreakoutStrategy(
        None,
        {
            "breakout_lookback": "2",
            "atr_period": "2",
            "atr_mult": "0.5",
            "allow_short": "true",
            "confidence": "0.7",
            "horizon": "5m",
            "volatility_regime": "normal",
        },
    )

    assert list(strategy.on_candle(_candle(1, 100.0, high=101.0, low=99.0))) == []
    assert list(strategy.on_candle(_candle(2, 100.0, high=101.0, low=99.0))) == []
    assert list(strategy.on_candle(_candle(3, 100.0, high=101.0, low=99.0))) == []
    signals = list(strategy.on_candle(_candle(4, 110.0, high=112.0, low=108.0)))
    assert len(signals) == 1
    assert signals[0].direction == "LONG"


def test_liquidity_reversal_on_volume_spike() -> None:
    strategy = LiquidityReversalStrategy(
        None,
        {
            "return_lookback": "1",
            "volume_lookback": "3",
            "return_threshold": "0.02",
            "volume_spike_ratio": "1.5",
            "cooldown_bars": "0",
            "allow_short": "true",
            "confidence": "0.6",
            "horizon": "5m",
            "volatility_regime": "normal",
        },
    )

    assert list(strategy.on_candle(_candle(1, 100.0, volume=100.0))) == []
    assert list(strategy.on_candle(_candle(2, 100.0, volume=100.0))) == []
    assert list(strategy.on_candle(_candle(3, 100.0, volume=100.0))) == []
    signals = list(strategy.on_candle(_candle(4, 103.0, volume=250.0)))
    assert len(signals) == 1
    assert signals[0].direction == "SHORT"
