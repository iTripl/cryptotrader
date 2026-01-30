from __future__ import annotations

import os
import re
from pathlib import Path


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def resolve_placeholders(value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return _ENV_PATTERN.sub(_replace, value)


def resolve_mapping(data: dict[str, str]) -> dict[str, str]:
    return {key: resolve_placeholders(value) for key, value in data.items()}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
