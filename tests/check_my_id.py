import sys
import io
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from core.runtime import config

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

if not config.WECHAT_MSG_DB:
    raise SystemExit("请先在 .env 配置 WECHAT_MSG_DB")
m_conn = sqlite3.connect(config.WECHAT_MSG_DB)
mc = m_conn.cursor()

tables = [r[0] for r in mc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%' LIMIT 30;").fetchall()]
for t in tables:
    mc.execute(f"SELECT DISTINCT status FROM {t};")
    st = [x[0] for x in mc.fetchall()]
    if any(s != 3 for s in st):
        print(f"Table {t} has non-3 status: {st}")
        # check those non-3 messages!
        mc.execute(f"SELECT local_id, create_time, message_content, real_sender_id, status FROM {t} WHERE status != 3 LIMIT 5;")
        for r in mc.fetchall():
            print("   non-3:", r)

m_conn.close()
