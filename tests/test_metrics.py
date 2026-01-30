from risk.metrics import compute_exposure, update_daily_drawdown
from state.models import PortfolioState, Position


def test_compute_exposure_uses_last_price() -> None:
    positions = {
        "BTCUSDT": Position(
            symbol="BTCUSDT",
            quantity=1.0,
            entry_price=100.0,
            side="LONG",
            max_price=100.0,
            min_price=100.0,
        )
    }
    snapshot = compute_exposure(positions, {"BTCUSDT": 110.0}, equity=1000.0)
    assert snapshot.gross_notional == 110.0
    assert snapshot.net_notional == 110.0
    assert snapshot.gross_exposure == 0.11
    assert snapshot.correlation == 1.0


def test_update_daily_drawdown_rolls_day() -> None:
    portfolio = PortfolioState(equity=1000.0, daily_drawdown=0.0, consecutive_losses=0)
    update_daily_drawdown(portfolio, 2 * 86400)
    assert portfolio.daily_start_equity == 1000.0
    assert portfolio.daily_peak_equity == 1000.0

    portfolio.equity = 900.0
    update_daily_drawdown(portfolio, 2 * 86400 + 3600)
    assert round(portfolio.daily_drawdown, 2) == 0.1

    portfolio.equity = 950.0
    update_daily_drawdown(portfolio, 3 * 86400)
    assert portfolio.daily_start_equity == 950.0
