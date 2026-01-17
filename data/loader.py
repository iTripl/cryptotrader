# data/loader.py
import pandas as pd
from .intervals import interval_to_ms
from .schemas import validate_ohlcv_schema
from .validator import OHLCVValidator

class MarketDataLoader:
    def __init__(self, source, storage, limit=1000, strict_validation=False):
        self.source = source
        self.storage = storage
        self.interval_min = interval_min
        self.limit = limit
        self.validator = OHLCVValidator(interval_min, strict=strict_validation)

    def load_range(self, symbol, interval_min, start_ts, end_ts) -> pd.DataFrame:
        cached = self.storage.load(symbol, interval_min, start_ts, end_ts)
        if cached is not None and not cached.empty:
            min_ts = int(cached["timestamp"].iloc[0].timestamp() * 1000)
            max_ts = int(cached["timestamp"].iloc[-1].timestamp() * 1000)
        else:
            cached = pd.DataFrame(columns=["timestamp","open","high","low","close","volume"])
            min_ts, max_ts = None, None

        to_fetch = []
        if min_ts is None or min_ts > start_ts:
            to_fetch.append((start_ts, min_ts - 1 if min_ts else end_ts))
        if max_ts is None or max_ts < end_ts:
            to_fetch.append((max_ts + 1 if max_ts else start_ts, end_ts))

        interval_ms = interval_to_ms(interval_min)
        window_ms = interval_ms * self.limit

        fetched_parts = []
        for s, e in to_fetch:
            cur = s
            while cur < e:
                cur_end = min(cur + window_ms - 1, e)
                df = self.source.fetch_ohlcv(
                    symbol, interval_min, cur, cur_end, self.limit
                )
                if df.empty:
                    cur += window_ms
                    continue

                fetched_parts.append(df)
                cur = int(df["timestamp"].iloc[-1].timestamp() * 1000) + 1

        if fetched_parts:
            fetched = validate_ohlcv_schema(pd.concat(fetched_parts))
            self.storage.save(symbol, interval_min, fetched)
            cached = pd.concat([cached, fetched]).drop_duplicates("timestamp")

        report = self.validator.validate(df)
        return df, report