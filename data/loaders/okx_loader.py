from __future__ import annotations

from data.loaders.base_loader import HistoricalLoader, PaginationState
from exchanges.okx.adapter import OkxAdapter


class OkxHistoricalLoader(HistoricalLoader):
    def __init__(self, adapter: OkxAdapter, checkpoint_path: str) -> None:
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
        rows = self.adapter.rest.get_ohlcv(symbol, timeframe, since, end_ts, limit)
        next_since = rows[-1]["timestamp"] + 1 if rows else since
        done = len(rows) < limit or next_since >= end_ts
        return rows, PaginationState(next_since=next_since, done=done)
