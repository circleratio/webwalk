"""百人一首 決まり字 暗記トレーナー CLI エントリポイント。

    python -m kimariji
"""

from __future__ import annotations

import argparse
from pathlib import Path

from kimariji.stats import DEFAULT_STATS_PATH
from kimariji.tui import main as run_tui


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="百人一首 決まり字 暗記トレーナー")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATS_PATH,
        help=f"成績の保存先ファイル（既定: {DEFAULT_STATS_PATH}）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_tui(stats_path=args.state_file)


if __name__ == "__main__":
    main()
