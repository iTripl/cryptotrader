from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from data.schemas import Candle
from utils.time import timeframe_to_seconds


@dataclass(frozen=True)
class ValidationIssue:
    classification: str
    severity: str
    message: str
    auto_fixable: bool = False


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    fixed: bool

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)


class CandleValidator:
    def validate(
        self,
        candles: Iterable[Candle],
        timeframe: str,
        auto_fix: bool = False,
    ) -> tuple[list[Candle], ValidationReport]:
        candles_list = list(candles)
        issues: list[ValidationIssue] = []
        fixed = False

        if not candles_list:
            issues.append(
                ValidationIssue(
                    classification="empty",
                    severity="error",
                    message="No candles provided",
                )
            )
            return candles_list, ValidationReport(tuple(issues), fixed)

        timestamps = [c.timestamp for c in candles_list]
        duplicate_ts = {ts for ts in timestamps if timestamps.count(ts) > 1}
        if duplicate_ts:
            issues.append(
                ValidationIssue(
                    classification="duplicates",
                    severity="warning",
                    message=f"Duplicate timestamps detected: {len(duplicate_ts)}",
                    auto_fixable=True,
                )
            )
            if auto_fix:
                seen = set()
                candles_list = [c for c in candles_list if not (c.timestamp in seen or seen.add(c.timestamp))]
                fixed = True

        expected_step = timeframe_to_seconds(timeframe)
        sorted_candles = sorted(candles_list, key=lambda c: c.timestamp)
        for prev, nxt in zip(sorted_candles, sorted_candles[1:]):
            gap = nxt.timestamp - prev.timestamp
            if gap != expected_step:
                issues.append(
                    ValidationIssue(
                        classification="gap",
                        severity="error",
                        message=f"Gap detected: {prev.timestamp} -> {nxt.timestamp} ({gap}s)",
                    )
                )
                break

        for candle in candles_list:
            if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close):
                issues.append(
                    ValidationIssue(
                        classification="ohlc",
                        severity="error",
                        message=f"OHLC inconsistency at {candle.timestamp}",
                    )
                )
                break
            if candle.volume < 0:
                issues.append(
                    ValidationIssue(
                        classification="volume",
                        severity="error",
                        message=f"Negative volume at {candle.timestamp}",
                    )
                )
                break

        exchanges = {c.exchange for c in candles_list}
        if len(exchanges) > 1:
            issues.append(
                ValidationIssue(
                    classification="exchange",
                    severity="error",
                    message="Multiple exchanges present in candle batch",
                )
            )

        return candles_list, ValidationReport(tuple(issues), fixed)
