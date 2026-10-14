import sqlite3
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))
import config

print("--- Checking decrypted databases ---")
base_dir = os.path.dirname(os.path.dirname(config.WECHAT_MSG_DB))
if not base_dir:
    raise SystemExit("请先在 .env 配置 WECHAT_MSG_DB")
for item in os.listdir(base_dir):
    p = os.path.join(base_dir, item)
    if os.path.isdir(p):
        for f in os.listdir(p):
            if f.endswith(".db"):
                print("DB:", item, f)

# Check session.db to see recent sessions!
session_db = os.path.join(base_dir, "session", "session.db")
if os.path.exists(session_db):
    s_conn = sqlite3.connect(session_db)
    sc = s_conn.cursor()
    sc.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print("Session tables:", sc.fetchall())
    # Query recent sessions
    try:
        sc.execute("SELECT * FROM session ORDER BY last_timestamp DESC LIMIT 10;")
        print("Session sample cols:", [d[0] for d in sc.description])
        for r in sc.fetchall():
            print("Session row:", r)
    except Exception as e:
        print("Session err:", e)
    s_conn.close()
