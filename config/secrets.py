from __future__ import annotations

import os
import re


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def resolve_placeholders(value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return _ENV_PATTERN.sub(_replace, value)


def resolve_mapping(data: dict[str, str]) -> dict[str, str]:
    return {key: resolve_placeholders(value) for key, value in data.items()}
