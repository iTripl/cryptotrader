from __future__ import annotations


def require_int(params: dict[str, str], key: str) -> int:
    if key not in params:
        raise ValueError(f"Missing strategy param: {key}")
    return int(params[key])


def require_float(params: dict[str, str], key: str) -> float:
    if key not in params:
        raise ValueError(f"Missing strategy param: {key}")
    return float(params[key])


def require_str(params: dict[str, str], key: str) -> str:
    if key not in params:
        raise ValueError(f"Missing strategy param: {key}")
    return str(params[key])
