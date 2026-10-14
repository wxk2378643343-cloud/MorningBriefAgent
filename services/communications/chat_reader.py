"""WeChat database adapter and normalized chat extraction."""

from __future__ import annotations

import datetime
import hashlib
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from typing import Any, Dict, List, Tuple

try:
    import zstandard as zstd
    _zstd_dctx = zstd.ZstdDecompressor()
except ImportError:
    _zstd_dctx = None


def sync_wechat_database(
    tools_dir: str,
    decrypt_script: str,
    timeout: int = 45,
) -> bool:
    """Run the optional local decrypt/sync command."""
    print("🔄 [Step 1/5] 同步微信本地数据库...")
    if not os.path.exists(decrypt_script):
        print(f"⚠️ 解密脚本不存在: {decrypt_script}，跳过同步，使用现有解密库")
        return False
    try:
        kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            kwargs["startupinfo"] = startup
        result = subprocess.run(
            [sys.executable, decrypt_script],
            cwd=tools_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            **kwargs,
        )
        if result.returncode == 0:
            print("✅ 微信数据库全量本地同步解密成功！")
            return True
        print(f"⚠️ 数据库解密警告: {result.stderr[:200]}")
    except Exception as exc:
        print(f"⚠️ 自动同步解密异常: {exc}，继续使用当前解密库")
    return False


def get_contact_maps(
    contact_db: str,
    excluded_usernames: Tuple[str, ...] = (),
    excluded_name_keywords: Tuple[str, ...] = (),
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return friend and chatroom display-name maps."""
    friends: Dict[str, str] = {}
    chatrooms: Dict[str, str] = {}
    if not os.path.exists(contact_db):
        return friends, chatrooms
    try:
        with closing(sqlite3.connect(contact_db)) as connection:
            rows = connection.execute(
                "SELECT username, remark, nick_name FROM contact"
            ).fetchall()
        for username, remark, nickname in rows:
            display = (
                remark.strip() if remark and remark.strip()
                else nickname.strip() if nickname and nickname.strip()
                else username
            )
            if username.endswith("@chatroom"):
                chatrooms[username] = display
            elif (
                username not in excluded_usernames
                and not any(keyword in display for keyword in excluded_name_keywords)
                and not (
                    username.startswith("gh_")
                    or username.endswith("@app")
                    or username in ("notifymessage", "fmessage", "newsapp", "weixin")
                )
            ):
                friends[username] = display
    except Exception as exc:
        print(f"⚠️ 读取联系人失败: {exc}")
    return friends, chatrooms


def _try_decompress(raw: bytes) -> str:
    if _zstd_dctx is not None:
        try:
            return _zstd_dctx.decompress(raw).decode("utf-8", errors="replace")
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def decode_message_content(content: Any, local_type: int) -> Tuple[str, str]:
    """Convert a raw WeChat message to an icon and safe display text."""
    if isinstance(content, bytes):
        if not content:
            return "❓", ""
        content = _try_decompress(content)
    if not isinstance(content, str):
        return "❓", ""
    text = content.strip()
    if ":\n" in text[:60]:
        prefix = text.split(":\n", 1)[0]
        if prefix.startswith("wxid_") or (
            len(prefix) < 25 and prefix.replace("_", "").isalnum()
        ):
            text = text.split(":\n", 1)[1].strip()

    if local_type == 3:
        return "📷", "[图片/截图]"
    if local_type == 47:
        match = re.search(r'<emoji[^>]*?desc=["\']([^"\']{1,30})["\']', text, re.I)
        return "🎭", f"[{match.group(1) if match else '动画表情/表情包'}]"
    if local_type == 43:
        return "🎬", "[视频消息]"
    if local_type == 34:
        return "🎙️", "[语音消息]"
    if local_type == 49 or text.startswith("<?xml") or text.startswith("<msg>") or "<appmsg" in text:
        title = re.search(r"<title>(.*?)</title>", text, re.S)
        url = re.search(r"<url>(.*?)</url>", text, re.S)
        title_text = title.group(1).strip()[:50] if title else "链接/卡片"
        url_text = f" → {url.group(1).strip()[:80]}" if url else ""
        return "🔗", f"[分享: {title_text}]{url_text}"
    return ("❓", "") if not text else ("💬", text)


def clean_text_content(content: Any) -> str:
    return decode_message_content(content, 1)[1]


def _table_exists(cursor, table_name: str) -> bool:
    return bool(cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone())


def scan_private_chats(
    message_db: str,
    friends_map: Dict[str, str],
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, Any]]:
    print("🔍 [Step 2/5] 全量扫描 1v1 好友私聊记录...")
    result = []
    if not os.path.exists(message_db):
        return result
    try:
        with closing(sqlite3.connect(message_db)) as connection:
            cursor = connection.cursor()
            for username, name in friends_map.items():
                table = f"Msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
                if not _table_exists(cursor, table):
                    continue
                rows = cursor.execute(
                    f"SELECT create_time, status, local_type, message_content "
                    f"FROM {table} WHERE create_time >= ? AND create_time <= ? "
                    "ORDER BY create_time ASC",
                    (start_ts, end_ts),
                ).fetchall()
                if not rows:
                    continue
                all_messages, my_messages, friend_messages = [], [], []
                for timestamp, status, local_type, raw_content in rows:
                    icon, text = decode_message_content(raw_content, local_type)
                    if not text:
                        continue
                    item = (
                        datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M"),
                        "本人" if status == 2 else name,
                        text,
                        icon,
                    )
                    all_messages.append(item)
                    (my_messages if status == 2 else friend_messages).append(item)
                if all_messages:
                    result.append({
                        "username": username,
                        "name": name,
                        "total_count": len(rows),
                        "text_count": len(all_messages),
                        "my_count": len(my_messages),
                        "friend_count": len(friend_messages),
                        "time_span": (
                            f"{datetime.datetime.fromtimestamp(rows[0][0]):%H:%M}"
                            f"~{datetime.datetime.fromtimestamp(rows[-1][0]):%H:%M}"
                        ),
                        "messages": all_messages,
                        "my_messages": my_messages,
                        "friend_messages": friend_messages,
                    })
    except Exception as exc:
        print(f"⚠️ 私聊扫描异常: {exc}")
    result.sort(key=lambda item: item["total_count"], reverse=True)
    return result


def scan_target_group_chats(
    message_db: str,
    chatrooms_map: Dict[str, str],
    start_ts: int,
    end_ts: int,
    specified_group_keywords: Tuple[str, ...] = (),
) -> Tuple[List[Dict[str, Any]], int]:
    print("🔍 [Step 3/5] 扫描群聊（严格白名单过滤）...")
    result = []
    total_groups = len(chatrooms_map)
    if not os.path.exists(message_db):
        return result, total_groups
    try:
        with closing(sqlite3.connect(message_db)) as connection:
            cursor = connection.cursor()
            for username, name in chatrooms_map.items():
                table = f"Msg_{hashlib.md5(username.encode('utf-8')).hexdigest()}"
                if not _table_exists(cursor, table):
                    continue
                my_count = cursor.execute(
                    f"SELECT count(*) FROM {table} WHERE status=2 "
                    "AND create_time >= ? AND create_time <= ?",
                    (start_ts, end_ts),
                ).fetchone()[0]
                selected = my_count > 0 or any(
                    keyword.lower() in name.lower()
                    for keyword in specified_group_keywords
                )
                if not selected:
                    continue
                rows = cursor.execute(
                    f"SELECT create_time, status, local_type, message_content "
                    f"FROM {table} WHERE create_time >= ? AND create_time <= ? "
                    "ORDER BY create_time ASC",
                    (start_ts, end_ts),
                ).fetchall()
                if not rows:
                    continue
                mine, others = [], []
                for timestamp, status, local_type, raw_content in rows:
                    icon, text = decode_message_content(raw_content, local_type)
                    if not text:
                        continue
                    item = (
                        datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M"),
                        "【本人】" if status == 2 else "群友",
                        text,
                        icon,
                    )
                    (mine if status == 2 else others).append(item)
                result.append({
                    "username": username,
                    "name": name,
                    "is_spoke": my_count > 0,
                    "my_count": len(mine),
                    "total_count": len(rows),
                    "my_messages": mine,
                    "other_messages": others,
                })
    except Exception as exc:
        print(f"⚠️ 群聊扫描异常: {exc}")
    result.sort(key=lambda item: (item["is_spoke"], item["total_count"]), reverse=True)
    return result, total_groups
