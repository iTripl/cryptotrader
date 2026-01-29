from __future__ import annotations

from data.loaders.base_loader import HistoricalLoader, PaginationState
from exchanges.bybit.adapter import BybitAdapter


class BybitHistoricalLoader(HistoricalLoader):
    def __init__(self, adapter: BybitAdapter, checkpoint_path: str) -> None:
        super().__init__(exchange_name=adapter.name, checkpoint=adapter.checkpoint(checkpoint_path))
        self.adapter = adapter

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int,
        end_ts: int,
        limit: int,
    ) -> tuple[list[dict], PaginationState]:
        rows, next_since = self.adapter.rest.get_ohlcv(symbol, timeframe, since, end_ts, limit)
        done = len(rows) < limit or (next_since is not None and next_since >= end_ts)
        return rows, PaginationState(next_since=next_since or since, done=done)
