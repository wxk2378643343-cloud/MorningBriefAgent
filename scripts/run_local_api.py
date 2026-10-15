"""Start the loopback API used by the local desktop workbench."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Support launching this file directly from Tauri, PowerShell, or Explorer.
# Python otherwise puts only ``scripts`` on sys.path, not the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.application.local_api import create_local_server
from storage.sqlite import initialize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MorningBrief local API")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="SQLite path; defaults to the configured local database",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_path = initialize(args.database)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = create_local_server(database_path=database_path, port=args.port)
    logging.info("local API listening on http://127.0.0.1:%s", server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("stopping local API")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
