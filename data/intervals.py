# data/intervals.py

BYBIT_INTERVAL_MAP = {
    1: "1",
    3: "3",
    5: "5",
    15: "15",
    30: "30",
    60: "60",
    240: "240",
    1440: "D",
}

def interval_to_ms(interval_min: int) -> int:
    return interval_min * 60 * 1000
