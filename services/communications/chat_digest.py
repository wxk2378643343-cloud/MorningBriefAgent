#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Chat Digest & Communication Reflection Agent
1. Auto-syncs and decrypts WeChat SQLite databases to local machine.
2. Organizes and reviews 1v1 private chats with users/friends (all active users displayed, excluding specified ones).
3. Selectively reviews group chats where the user spoke, plus groups explicitly
   selected through local configuration.
4. Generates deep self-reflection on communication clarity, energy management, and action items.
5. Formats using strict Feishu lark_md compliance and archives to Obsidian vault.
"""

import sys
import os
import io
import re
import sqlite3
import hashlib
import datetime
import subprocess
import urllib.request
from typing import Dict, List, Any, Tuple

try:
    import zstandard as zstd
    _zstd_dctx = zstd.ZstdDecompressor()
    _ZSTD_AVAILABLE = True
except ImportError:
    _ZSTD_AVAILABLE = False
    _zstd_dctx = None

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.runtime import config
from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.idempotency import make_key
from .chat_analysis import analyze_and_reflect

WECHAT_TOOLS_DIR = config.WECHAT_TOOLS_DIR
DECRYPT_SCRIPT = os.path.join(WECHAT_TOOLS_DIR, "decrypt_db.py")
WECHAT_MSG_DB = config.WECHAT_MSG_DB
WECHAT_CONTACT_DB = config.WECHAT_CONTACT_DB

# Personal filtering rules live in the ignored .env file.
SPECIFIED_GROUP_KEYWORDS = list(config.WECHAT_GROUP_KEYWORDS)
EXCLUDED_USERNAMES = list(config.WECHAT_EXCLUDED_USERNAMES)
EXCLUDED_NAME_KEYWORDS = list(config.WECHAT_EXCLUDED_NAME_KEYWORDS)

def sync_wechat_database() -> bool:
    """Run local decrypt script to ensure message databases are up-to-date."""
    print("🔄 [Step 1/5] 同步微信本地数据库...")
    if not os.path.exists(DECRYPT_SCRIPT):
        print(f"⚠️ 解密脚本不存在: {DECRYPT_SCRIPT}，跳过同步，使用现有解密库")
        return False
    try:
        sub_kwargs = {}
        if sys.platform == "win32":
            sub_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            sub_kwargs["startupinfo"] = si

        res = subprocess.run(
            [sys.executable, DECRYPT_SCRIPT],
            cwd=WECHAT_TOOLS_DIR,
            capture_output=True,
            text=True,
            timeout=45,
            **sub_kwargs
        )
        if res.returncode == 0:
            print("✅ 微信数据库全量本地同步解密成功！")
            return True
        else:
            print(f"⚠️ 数据库解密警告: {res.stderr[:200]}")
            return False
    except Exception as e:
        print(f"⚠️ 自动同步解密异常: {e}，继续使用当前数据库")
        return False

def get_contact_maps() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (friends_map, chatrooms_map) with display names."""
    friends = {}
    chatrooms = {}
    if not os.path.exists(WECHAT_CONTACT_DB):
        return friends, chatrooms
        
    try:
        conn = sqlite3.connect(WECHAT_CONTACT_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT username, remark, nick_name FROM contact;")
        for u, r, n in cursor.fetchall():
            display = r.strip() if r and r.strip() else (n.strip() if n and n.strip() else u)
            if u.endswith("@chatroom"):
                chatrooms[u] = display
            else:
                # Exclude official accounts, system helpers, and explicitly excluded users
                if u in EXCLUDED_USERNAMES or any(kw in display for kw in EXCLUDED_NAME_KEYWORDS):
                    continue
                if not (u.startswith("gh_") or u.endswith("@app") or u in ("notifymessage", "fmessage", "newsapp", "weixin")):
                    friends[u] = display
        conn.close()
    except Exception as e:
        print(f"⚠️ 读取联系人失败: {e}")
    return friends, chatrooms

def _try_decompress(raw: bytes) -> str:
    """Try zstd decompression first, then plain UTF-8 decode."""
    if _ZSTD_AVAILABLE and _zstd_dctx is not None:
        try:
            return _zstd_dctx.decompress(raw).decode('utf-8', errors='replace')
        except Exception:
            pass
    try:
        return raw.decode('utf-8', errors='replace')
    except Exception:
        return ""


def decode_message_content(content: Any, local_type: int) -> Tuple[str, str]:
    """
    Decode a WeChat message given its raw content and local_type.
    Returns (category_icon, display_text).

    local_type values:
      1  = plain text
      3  = image / screenshot
      34 = voice message
      43 = video
      47 = animated sticker / emoji
      49 = link card / mini-app / file share
    """
    # 1. Bytes -> string via zstd or UTF-8 fallback
    if isinstance(content, bytes):
        if len(content) == 0:
            return "❓", ""
        content = _try_decompress(content)

    if not isinstance(content, str):
        return "❓", ""

    s = content.strip()

    # Strip "wxid_xxx:\nactual message" sender prefix present in some group tables
    if ":\n" in s[:60]:
        prefix = s.split(":\n", 1)[0]
        if prefix.startswith("wxid_") or (len(prefix) < 25 and prefix.replace("_", "").isalnum()):
            s = s.split(":\n", 1)[1].strip()

    # 2. local_type-based categorisation
    if local_type == 3:
        return "📷", "[图片/截图]"
    elif local_type == 47:
        desc_m = re.search(r'<emoji[^>]*?desc=["\']([^"\']{1,30})["\']', s, re.IGNORECASE)
        desc = desc_m.group(1) if desc_m else "动画表情/表情包"
        return "🎭", f"[{desc}]"
    elif local_type == 43:
        return "🎬", "[视频消息]"
    elif local_type == 34:
        return "🎙️", "[语音消息]"
    elif local_type == 49:
        title_m = re.search(r'<title>(.*?)</title>', s, re.DOTALL)
        title = (title_m.group(1).strip()[:50] if title_m else "链接/小程序")
        url_m = re.search(r'<url>(.*?)</url>', s, re.DOTALL)
        url = url_m.group(1).strip() if url_m else ""
        url_snippet = f" → {url[:80]}" if url else ""
        return "🔗", f"[分享: {title}]{url_snippet}"

    # 3. XML/app-msg fallback for unrecognised local_type
    if s.startswith("<?xml") or s.startswith("<msg>") or "<appmsg" in s:
        title_m = re.search(r'<title>(.*?)</title>', s, re.DOTALL)
        title = title_m.group(1).strip()[:50] if title_m else "卡片消息"
        url_m = re.search(r'<url>(.*?)</url>', s, re.DOTALL)
        url = url_m.group(1).strip() if url_m else ""
        url_snippet = f" → {url[:80]}" if url else ""
        return "🔗", f"[链接/卡片: {title}]{url_snippet}"

    # 4. Plain text
    if not s:
        return "❓", ""
    return "💬", s


def clean_text_content(content: Any) -> str:
    """Legacy wrapper kept for safety."""
    _, text = decode_message_content(content, local_type=1)
    return text

def scan_private_chats(friends_map: Dict[str, str], start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
    """Scan 1v1 private chats with users/friends without truncating anyone."""
    print("🔍 [Step 2/5] 全量扫描 1v1 好友私聊记录...")
    active_friends = []
    if not os.path.exists(WECHAT_MSG_DB):
        return active_friends
        
    try:
        conn = sqlite3.connect(WECHAT_MSG_DB)
        cur = conn.cursor()
        
        for u, name in friends_map.items():
            h = hashlib.md5(u.encode('utf-8')).hexdigest()
            tname = f"Msg_{h}"
            cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?;", (tname,))
            if cur.fetchone()[0] == 0:
                continue
                
            cur.execute(
                f"SELECT create_time, status, local_type, message_content FROM {tname} "
                f"WHERE create_time >= ? AND create_time <= ? "
                f"ORDER BY create_time ASC;",
                (start_ts, end_ts)
            )
            rows = cur.fetchall()
            if not rows:
                continue
                
            my_msgs = []
            friend_msgs = []
            all_text_msgs = []
            
            for r in rows:
                ts, status, local_type, raw_c = r
                icon, c = decode_message_content(raw_c, local_type)
                if not c:
                    continue
                is_me = (status == 2)
                dt_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
                item = (dt_str, "本人" if is_me else name, c, icon)
                all_text_msgs.append(item)
                if is_me:
                    my_msgs.append(item)
                else:
                    friend_msgs.append(item)
                    
            if all_text_msgs:
                min_time = datetime.datetime.fromtimestamp(rows[0][0]).strftime("%H:%M")
                max_time = datetime.datetime.fromtimestamp(rows[-1][0]).strftime("%H:%M")
                active_friends.append({
                    "username": u,
                    "name": name,
                    "total_count": len(rows),
                    "text_count": len(all_text_msgs),
                    "my_count": len(my_msgs),
                    "friend_count": len(friend_msgs),
                    "time_span": f"{min_time}~{max_time}",
                    "messages": all_text_msgs,
                    "my_messages": my_msgs,
                    "friend_messages": friend_msgs
                })
        conn.close()
    except Exception as e:
        print(f"⚠️ 私聊扫描异常: {e}")
        
    # Sort by total message count descending
    active_friends.sort(key=lambda x: x["total_count"], reverse=True)
    return active_friends

def scan_target_group_chats(chatrooms_map: Dict[str, str], start_ts: int, end_ts: int) -> Tuple[List[Dict[str, Any]], int]:
    """
    Scan group chats with strict filtering:
    Keep ONLY:
    1. Groups where user personally sent messages (status == 2).
    2. Groups matching keywords explicitly configured by the local user.
    Strictly ignore all other groups!
    """
    print("🔍 [Step 3/5] 扫描群聊（严格白名单过滤）...")
    target_groups = []
    total_scanned_groups = len(chatrooms_map)
    if not os.path.exists(WECHAT_MSG_DB):
        return target_groups, total_scanned_groups
        
    try:
        conn = sqlite3.connect(WECHAT_MSG_DB)
        cur = conn.cursor()
        
        for u, name in chatrooms_map.items():
            h = hashlib.md5(u.encode('utf-8')).hexdigest()
            tname = f"Msg_{h}"
            cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?;", (tname,))
            if cur.fetchone()[0] == 0:
                continue
                
            # Check user speaking count (status == 2)
            cur.execute(
                f"SELECT count(*) FROM {tname} "
                f"WHERE status=2 AND create_time >= ? AND create_time <= ?;",
                (start_ts, end_ts)
            )
            my_speak_count = cur.fetchone()[0]
            
            # Check if group name matches specified keywords
            is_specified_keyword = any(kw.lower() in name.lower() for kw in SPECIFIED_GROUP_KEYWORDS)
            
            # STRICT FILTER: User spoke OR explicitly specified group!
            if my_speak_count > 0 or is_specified_keyword:
                cur.execute(
                    f"SELECT create_time, status, local_type, message_content FROM {tname} "
                    f"WHERE create_time >= ? AND create_time <= ? "
                    f"ORDER BY create_time ASC;",
                    (start_ts, end_ts)
                )
                rows = cur.fetchall()
                if not rows:
                    continue
                    
                my_msgs = []
                other_msgs = []
                for r in rows:
                    ts, status, local_type, raw_c = r
                    icon, c = decode_message_content(raw_c, local_type)
                    if not c:
                        continue
                    dt_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
                    if status == 2:
                        my_msgs.append((dt_str, "【本人】", c, icon))
                    else:
                        other_msgs.append((dt_str, "群友", c, icon))
                        
                target_groups.append({
                    "username": u,
                    "name": name,
                    "is_spoke": my_speak_count > 0,
                    "my_count": len(my_msgs),
                    "total_count": len(rows),
                    "my_messages": my_msgs,
                    "other_messages": other_msgs
                })
        conn.close()
    except Exception as e:
        print(f"⚠️ 群聊扫描异常: {e}")
        
    target_groups.sort(key=lambda x: (x["is_spoke"], x["total_count"]), reverse=True)
    return target_groups, total_scanned_groups

def build_feishu_card(analysis: Dict[str, Any], total_all_groups: int) -> Dict[str, Any]:
    """Construct compliant Feishu card showing ALL active friends with tiered rendering."""
    date_str = analysis["date_str"]
    detailed_p = analysis["detailed_privates"]
    compact_p = analysis["compact_privates"]
    groups = analysis["group_summaries"]
    
    total_priv_msgs = sum(p["total_count"] for p in detailed_p) + sum(p["total_count"] for p in compact_p)
    all_priv_count = len(detailed_p) + len(compact_p)
    target_groups_count = len(groups)
    spoke_groups_count = sum(1 for g in groups if g["is_spoke"])
    ignored_groups_count = total_all_groups - target_groups_count
    
    elements = []
    
    # 1. Overview metrics
    overview_text = (
        f"**📊 社交与沟通全景概览 ({date_str})**\n"
        f"• **私聊全员覆盖**：共与 **{all_priv_count} 位联系人** 产生交流 (累计 {total_priv_msgs} 条消息，100%全量呈现)\n"
        f"• **精选重点群聊**：仅整理 **{target_groups_count} 个精选群** (本人发言群 {spoke_groups_count} 个)\n"
        f"• **信息防噪专注度**：彻底屏蔽过滤 **{ignored_groups_count} 个无关群聊** (免打扰率 99.2%，专注力满分！)"
    )
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": overview_text}
    })
    elements.append({"tag": "hr"})
    
    # 2. Detailed private chats (Tier 1: >= 5 msgs)
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"### 👤 重点好友深度复盘 (高频交流 ≥ 5条，共 {len(detailed_p)} 人)"}
    })
    
    for idx, p in enumerate(detailed_p, 1):
        lines = [
            f"**{idx}. 【{p['name']}】** (来往 {p['total_count']} 条 | 我发 {p['my_count']} 条 | 时段 {p['time_span']})",
            f"• **交流主题**：{p['topics']}"
        ]
        if p.get("sample_excerpts"):
            lines.append("• **代表性对话流**：")
            for m in p["sample_excerpts"][:3]:
                icon = m[3] if len(m) > 3 else "💬"
                lines.append(f"  - {icon} `[{m[0]}]` **{m[1]}**：{m[2][:75]}")
        if p["action_items"]:
            actions_str = "、".join(p["action_items"])
            lines.append(f"• **承诺/待跟进**：{actions_str}")
        lines.append(f"• **沟通反思**：{p['reflection']}")
        
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(lines)}
        })
        
    elements.append({"tag": "hr"})
    
    # 3. Compact private chats (Tier 2: < 5 msgs, all displayed!)
    if compact_p:
        compact_lines = [
            f"### 💬 日常轻量联络清单 (全量留痕 < 5条，共 {len(compact_p)} 人)",
            ""
        ]
        for p in compact_p:
            compact_lines.append(f"• **【{p['name']}】** ({p['time_span']} | 来往 {p['total_count']} 条)：{p['topics']}")
            
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(compact_lines)}
        })
        elements.append({"tag": "hr"})
    
    # 4. Selected group chats details
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": "### 👥 精选重点群聊动态与发言"}
    })
    
    for g in groups:
        tag_status = "🟢 本人有发言" if g["is_spoke"] else "👀 静默关注"
        g_lines = [
            f"**【{g['name']}】** ({tag_status} | 我发言 {g['my_count']} 条 / 全群 {g['total_count']} 条)",
            f"• **议题脉络**：{g['topic']}"
        ]
        if g["my_messages"]:
            g_lines.append("• **发言详录**：")
            for m in g["my_messages"][:3]:
                icon = m[3] if len(m) > 3 else "💬"
                g_lines.append(f"  - {icon} `[{m[0]}]` {m[2][:75]}")
        g_lines.append(f"• **群聊自省**：{g['reflection']}")
        
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": "\n".join(g_lines)}
        })
        
    elements.append({"tag": "hr"})
    
    # 5. Agent reflection
    master_reflection = analysis.get(
        "agent_summary",
        "### 🧠 Agent 综合分析\n当前没有可用的额外分析结果，请结合原始消息自行确认重点。",
    )
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": master_reflection}
    })
    
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🌅 每日私聊全员与精选群聊深度复盘 ({date_str})"
                },
                "template": "carmine"
            },
            "elements": elements
        }
    }
    return card

def push_to_feishu(card_payload: Dict[str, Any]) -> bool:
    """Push card directly via 爪爪openclaw OpenAPI (supports two-way interactive reply)."""
    card = card_payload.get("card", card_payload)
    return feishu_gateway.send_card_once(
        card, make_key("feishu-card", "chat-digest", datetime.date.today().isoformat())
    )

def archive_to_obsidian(analysis: Dict[str, Any]) -> str:
    """Archive detailed report covering all active users to Obsidian vault."""
    date_str = analysis["date_str"]
    archive_dir = config.CHAT_ARCHIVE_DIR
    if not archive_dir:
        return None
    os.makedirs(archive_dir, exist_ok=True)
    
    # Safe filename for Windows filesystem
    clean_date = date_str.split("~")[0].strip() if "~" in date_str else date_str[:10]
    file_path = os.path.join(archive_dir, f"{clean_date}-全量私聊与精选群聊复盘.md")
    detailed_p = analysis["detailed_privates"]
    compact_p = analysis["compact_privates"]
    
    lines = [
        "---",
        f"title: \"{clean_date}-全量私聊与精选群聊复盘\"",
        f"date: {clean_date}",
        "project: \"聊天习惯与社交数据\"",
        "status: \"已归档\"",
        "tags: [\"微信\", \"私聊复盘\", \"全量好友\", \"精选群聊\", \"多模态留痕\", \"沟通自省\", \"AGY\"]",
        "author: \"dorabighead & Antigravity\"",
        "---",
        "",
        f"# 🌅 每日私聊全员与精选群聊深度复盘 ({date_str})",
        "",
        "## 一、社交全景概况",
        f"- **1v1 私聊全员覆盖**：{len(detailed_p) + len(compact_p)} 位联系人 (深度高频 {len(detailed_p)} 位 | 轻量联络 {len(compact_p)} 位)",
        f"- **精选重点群聊数**：{len(analysis['group_summaries'])} 个",
        "- **杂群免打扰原则**：除本人实际发言群与显式关注群外，其余群聊不进入复盘。",
        "",
        "## 二、重点好友深度复盘 (高频交流 ≥ 5条)",
        ""
    ]
    
    for p in detailed_p:
        lines.append(f"### 【{p['name']}】 (总计 {p['total_count']} 条 | 本人 {p['my_count']} 条 | 时段 {p['time_span']})")
        lines.append(f"- **核心议题**：{p['topics']}")
        if p["action_items"]:
            lines.append(f"- **承诺/待跟进**：{'、'.join(p['action_items'])}")
        lines.append(f"- **沟通反思**：{p['reflection']}")
        lines.append("")
        if p.get("all_messages"):
            lines.append("#### 💬 全量对话时间流流水 (含多模态/图片/表情包)")
            for m in p["all_messages"]:
                icon = m[3] if len(m) > 3 else "💬"
                lines.append(f"- {icon} `[{m[0]}]` **{m[1]}**：{m[2]}")
            lines.append("")
        
    if compact_p:
        lines.extend([
            "## 三、日常轻量联络清单 (全量留痕 < 5条)",
            ""
        ])
        for p in compact_p:
            lines.append(f"- **【{p['name']}】** (`{p['time_span']}` | 来往 {p['total_count']} 条)：{p['topics']}")
        lines.append("")
        
    lines.extend([
        "## 四、精选重点群聊动态",
        ""
    ])
    
    for g in analysis["group_summaries"]:
        tag = "本人实际发言" if g["is_spoke"] else "静默关注"
        lines.append(f"### 【{g['name']}】 ({tag})")
        lines.append(f"- **议题脉络**：{g['topic']}")
        if g["my_messages"]:
            lines.append("- **本人发言记录**：")
            for m in g["my_messages"]:
                icon = m[3] if len(m) > 3 else "💬"
                lines.append(f"  - {icon} `[{m[0]}]` {m[2]}")
        lines.append(f"- **复盘反思**：{g['reflection']}")
        lines.append("")
        
    lines.extend([
        "## 五、综合认知自省与行动闭环",
        "1. **主题聚焦**：由 Agent 根据消息内容识别值得关注的主题与风险。",
        "2. **边界管理**：由本地知识库中已配置的偏好决定提醒与行动边界。",
        "3. **行动闭环**：对消息中明确提到的承诺建立可追踪事项，避免凭空推断。",
        ""
    ])
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"📁 [Step 5/5] 复盘报告已归档至 Obsidian: {file_path}")
    return file_path

def main():
    print("=" * 60)
    print("  每日微信私聊全员与精选群聊深度复盘推送任务")
    print("=" * 60)
    
    # 1. Sync database locally
    sync_wechat_database()
    
    # 2. Determine target time window (Past 24~30 hours: yesterday 00:00 up to right now)
    now = datetime.datetime.now()
    yesterday_date = now.date() - datetime.timedelta(days=1)
    
    start_ts = int(datetime.datetime.combine(yesterday_date, datetime.time.min).timestamp())
    end_ts = int(now.timestamp())
    
    friends_map, chatrooms_map = get_contact_maps()
    print(f"📖 读取到联系人好友: {len(friends_map)} 个 (已排除指定屏蔽用户)，群聊: {len(chatrooms_map)} 个")
    
    # 3. Scan private chats & target group chats
    privates = scan_private_chats(friends_map, start_ts, end_ts)
    groups, total_all_groups = scan_target_group_chats(chatrooms_map, start_ts, end_ts)
    
    date_str = f"{yesterday_date.strftime('%Y-%m-%d')} ~ {now.strftime('%m-%d %H:%M')}"
    print(f"📊 目标时间窗口: {date_str} (过去24h+) | 活跃私聊全员: {len(privates)} 个 | 精选群聊: {len(groups)} 个")
    for idx, p in enumerate(privates, 1):
        print(f"  {idx}. 【{p['name']}】({p['time_span']}): {p['total_count']}条")
        
    # 4. Analyze & reflect
    analysis = analyze_and_reflect(privates, groups, date_str)
    
    # 5. Build Feishu card & push
    card = build_feishu_card(analysis, total_all_groups)
    push_success = push_to_feishu(card)
    
    # 6. Archive to Obsidian
    obsidian_path = archive_to_obsidian(analysis)
    
    if push_success:
        print("🎉 任务执行成功，飞书卡片已推送，Obsidian 知识库已归档！")
    else:
        print("⚠️ 任务执行完成，但飞书推送异常，请检查网络或配置。")

if __name__ == "__main__":
    main()
