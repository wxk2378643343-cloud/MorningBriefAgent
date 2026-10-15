"""Initialize the local SQLite fact database without touching personal files."""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage.sqlite import initialize


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--demo",
        action="store_true",
        help="initialize the isolated demo database instead of the real database",
    )
    args = parser.parse_args()
    database = initialize(demo=args.demo)
    label = "demo" if args.demo else "real"
    print(f"✅ {label} SQLite facts database ready: {database}")
