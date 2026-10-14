
"""Manual server launch check. Run this file directly."""
import sys
import traceback
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    try:
        from server import feishu_bot_server
        feishu_bot_server.run_server()
    except Exception:
        log_dir = root / "logs"
        log_dir.mkdir(exist_ok=True)
        with (log_dir / "crash.log").open("w", encoding="utf-8") as crash_file:
            traceback.print_exc(file=crash_file)
        raise
