from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable

from data.normalization import normalize_ohlcv
from data.schemas import Candle
from data.validation import CandleValidator
from utils.logger import get_logger
from utils.time import timeframe_to_seconds


logger = get_logger("data.loader")


@dataclass(frozen=True)
class PaginationState:
    next_since: int
    done: bool


class LoaderCheckpoint:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> PaginationState | None:
        if not self._path.exists():
            return None
        with self._path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return PaginationState(**payload)

    def save(self, state: PaginationState) -> None:
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump({"next_since": state.next_since, "done": state.done}, handle)

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()


class HistoricalLoader:
    def __init__(
        self,
        exchange_name: str,
        checkpoint: LoaderCheckpoint,
        validator: CandleValidator | None = None,
    ) -> None:
        self.exchange_name = exchange_name
        self.checkpoint = checkpoint
        self.validator = validator or CandleValidator()

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int,
        end_ts: int,
        limit: int,
    ) -> tuple[list[dict], PaginationState]:
        raise NotImplementedError

    def load_range(
        self,
        symbol: str,
        timeframe: str,
        start_ts: int,
        end_ts: int,
        limit: int = 1000,
        auto_fix: bool = True,
        timeout_seconds: int | None = None,
        max_empty_batches: int = 2,
    ) -> Iterable[Candle]:
        state = self.checkpoint.load()
        if state and state.done and state.next_since >= end_ts:
            logger.info("loader checkpoint already complete for range")
            return []

        since = max(state.next_since, start_ts) if state else start_ts
        timeframe_step = timeframe_to_seconds(timeframe)
        started_at = time.time()
        empty_batches = 0

        while since < end_ts:
            prev_since = since
            if timeout_seconds is not None and (time.time() - started_at) > timeout_seconds:
                raise TimeoutError("data load timed out")
            rows, pagination = self.fetch_ohlcv(symbol, timeframe, since, end_ts, limit)
            if not rows:
                logger.warning("empty batch returned; stopping loader")
                empty_batches += 1
                if empty_batches >= max_empty_batches:
                    raise RuntimeError("no data returned from exchange")
                break

            candles = normalize_ohlcv(rows, symbol, timeframe, self.exchange_name)
            candles, report = self.validator.validate(candles, timeframe, auto_fix=auto_fix)
            if not report.ok:
                logger.error("validation error: %s", report.issues)
                raise ValueError("validation failed")

            empty_batches = 0
            for candle in candles:
                if candle.timestamp >= end_ts:
                    break
                yield candle

            since = max(c.timestamp for c in candles) + timeframe_step
            if since <= prev_since:
                logger.warning("pagination stalled; stopping loader")
                break
            self.checkpoint.save(PaginationState(next_since=since, done=False))

            if pagination.done:
                break

        self.checkpoint.save(PaginationState(next_since=since, done=True))
