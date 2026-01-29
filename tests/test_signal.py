import pytest

from signals.signal import Signal


def test_signal_confidence_validation() -> None:
    with pytest.raises(ValueError):
        Signal(
            symbol="BTCUSDT",
            direction="LONG",
            confidence=1.5,
            horizon="5m",
            volatility_regime="normal",
            metadata={},
        )
