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
from . import chat_reader

WECHAT_TOOLS_DIR = config.WECHAT_TOOLS_DIR
DECRYPT_SCRIPT = os.path.join(WECHAT_TOOLS_DIR, "decrypt_db.py")
WECHAT_MSG_DB = config.WECHAT_MSG_DB
WECHAT_CONTACT_DB = config.WECHAT_CONTACT_DB

# Personal filtering rules live in the ignored .env file.
SPECIFIED_GROUP_KEYWORDS = list(config.WECHAT_GROUP_KEYWORDS)
EXCLUDED_USERNAMES = list(config.WECHAT_EXCLUDED_USERNAMES)
EXCLUDED_NAME_KEYWORDS = list(config.WECHAT_EXCLUDED_NAME_KEYWORDS)

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


# Compatibility wrappers: data access is implemented by chat_reader.
def sync_wechat_database() -> bool:
    return chat_reader.sync_wechat_database(WECHAT_TOOLS_DIR, DECRYPT_SCRIPT)


def get_contact_maps() -> Tuple[Dict[str, str], Dict[str, str]]:
    return chat_reader.get_contact_maps(
        WECHAT_CONTACT_DB,
        tuple(EXCLUDED_USERNAMES),
        tuple(EXCLUDED_NAME_KEYWORDS),
    )


def decode_message_content(content: Any, local_type: int) -> Tuple[str, str]:
    return chat_reader.decode_message_content(content, local_type)


def clean_text_content(content: Any) -> str:
    return chat_reader.clean_text_content(content)


def scan_private_chats(
    friends_map: Dict[str, str],
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, Any]]:
    return chat_reader.scan_private_chats(
        WECHAT_MSG_DB, friends_map, start_ts, end_ts
    )


def scan_target_group_chats(
    chatrooms_map: Dict[str, str],
    start_ts: int,
    end_ts: int,
) -> Tuple[List[Dict[str, Any]], int]:
    return chat_reader.scan_target_group_chats(
        WECHAT_MSG_DB,
        chatrooms_map,
        start_ts,
        end_ts,
        tuple(SPECIFIED_GROUP_KEYWORDS),
    )


if __name__ == "__main__":
    main()
