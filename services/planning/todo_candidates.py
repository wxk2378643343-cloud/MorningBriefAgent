"""Extract candidate todo items from configured local sources."""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
from typing import Iterable, List


def extract_candidates(
    *,
    sync_database,
    message_db: str,
    feishu_log: str,
    todo_path: str,
    keywords: Iterable[str],
    log_keywords: Iterable[str],
    limit: int = 6,
) -> List[str]:
    candidates: List[str] = []
    seen = set()
    try:
        sync_database()
    except Exception as exc:
        print(f"Sync WeChat db before extract warning: {exc}")

    today_start = datetime.datetime.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_ts = int(today_start.timestamp())
    if os.path.exists(message_db):
        try:
            with sqlite3.connect(message_db) as connection:
                tables = [
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name LIKE 'Msg_%'"
                    ).fetchall()
                ]
                for table in tables:
                    try:
                        rows = connection.execute(
                            f"SELECT message_content, create_time, status FROM {table} "
                            "WHERE create_time >= ? ORDER BY create_time DESC LIMIT 25",
                            (today_ts,),
                        ).fetchall()
                        for content, _created, _status in rows:
                            if not isinstance(content, str):
                                continue
                            text = content.strip()
                            if not 4 <= len(text) <= 80:
                                continue
                            if ":\n" in text[:30]:
                                text = text.split(":\n", 1)[1].strip()
                            if (
                                text.startswith(("<?xml", "<msg>", "http"))
                                or "<appmsg" in text
                            ):
                                continue
                            if any(keyword in text for keyword in keywords):
                                if text not in seen:
                                    seen.add(text)
                                    candidates.append(text)
                            if len(candidates) >= 5:
                                break
                    except sqlite3.Error:
                        continue
                    if len(candidates) >= 5:
                        break
        except sqlite3.Error as exc:
            print(f"WeChat scan exception: {exc}")

    if os.path.exists(feishu_log):
        try:
            with open(feishu_log, "r", encoding="utf-8", errors="replace") as file:
                for line in file:
                    if "收到飞书新消息" not in line or "内容: '" not in line:
                        continue
                    match = re.search(r"内容:\s*'([^']+)'", line)
                    if not match:
                        continue
                    text = match.group(1).strip()
                    if any(keyword in text for keyword in log_keywords):
                        if text not in seen and len(text) < 50:
                            seen.add(text)
                            candidates.append(text)
        except OSError as exc:
            print(f"Feishu log scan warning: {exc}")

    if todo_path and os.path.exists(todo_path):
        try:
            with open(todo_path, "r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line.startswith("- [ ]") or "**" not in line:
                        continue
                    match = re.search(r"\*\*(.*?)\*\*", line)
                    if match:
                        item = match.group(1).strip()
                        if item not in seen:
                            seen.add(item)
                            candidates.append(f"【顺延未完】{item}")
        except OSError as exc:
            print(f"Todo rollover scan warning: {exc}")

    return candidates[:limit]
