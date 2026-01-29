from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.bootstrap import Bootstrap
from config.loader import load_config
from console.menu import ConsoleMenu
from utils.logger import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CryptoTrader Infrastructure")
    parser.add_argument(
        "--config",
        default="config/config.ini",
        help="Path to config.ini",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive console menu",
    )
    parser.add_argument(
        "--mode",
        choices=["backtest", "forward", "live"],
        help="Override mode from config",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without execution",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)

    if args.mode:
        config = config.with_mode(args.mode)
    if args.dry_run:
        config = config.with_dry_run(True)

    if args.interactive:
        config = ConsoleMenu(config).run()

    configure_logging(config.logging, config.paths.logs_dir)

    app = Bootstrap(config).build()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
