"""Orchestrate the daily communication digest workflow."""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Tuple

from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.idempotency import make_key
from core.runtime import config

from . import chat_archive, chat_reader, chat_renderer
from .chat_analysis import analyze_and_reflect


WECHAT_TOOLS_DIR = config.WECHAT_TOOLS_DIR
DECRYPT_SCRIPT = os.path.join(WECHAT_TOOLS_DIR, "decrypt_db.py")
WECHAT_MSG_DB = config.WECHAT_MSG_DB
WECHAT_CONTACT_DB = config.WECHAT_CONTACT_DB
SPECIFIED_GROUP_KEYWORDS = list(config.WECHAT_GROUP_KEYWORDS)
EXCLUDED_USERNAMES = list(config.WECHAT_EXCLUDED_USERNAMES)
EXCLUDED_NAME_KEYWORDS = list(config.WECHAT_EXCLUDED_NAME_KEYWORDS)


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


def build_feishu_card(
    analysis: Dict[str, Any],
    total_all_groups: int,
) -> Dict[str, Any]:
    return chat_renderer.build_feishu_card(analysis, total_all_groups)


def push_to_feishu(card_payload: Dict[str, Any]) -> bool:
    """Publish the rendered card through the unified Feishu gateway."""
    card = card_payload.get("card", card_payload)
    return feishu_gateway.send_card_once(
        card,
        make_key("feishu-card", "chat-digest", datetime.date.today().isoformat()),
    )


def archive_to_obsidian(analysis: Dict[str, Any]) -> str | None:
    return chat_archive.archive_to_obsidian(analysis, config.CHAT_ARCHIVE_DIR)


def main() -> None:
    print("=" * 60)
    print("  每日微信私聊全员与精选群聊深度复盘推送任务")
    print("=" * 60)

    sync_wechat_database()
    now = datetime.datetime.now()
    yesterday = now.date() - datetime.timedelta(days=1)
    start_ts = int(datetime.datetime.combine(yesterday, datetime.time.min).timestamp())
    end_ts = int(now.timestamp())

    friends_map, chatrooms_map = get_contact_maps()
    print(
        f"📖 读取到联系人好友: {len(friends_map)} 个 "
        f"(已排除指定屏蔽用户)，群聊: {len(chatrooms_map)} 个"
    )
    private_chats = scan_private_chats(friends_map, start_ts, end_ts)
    group_chats, total_all_groups = scan_target_group_chats(
        chatrooms_map, start_ts, end_ts
    )
    date_str = f"{yesterday:%Y-%m-%d} ~ {now:%m-%d %H:%M}"
    print(
        f"📊 目标时间窗口: {date_str} (过去24h+) | "
        f"活跃私聊全员: {len(private_chats)} 个 | 精选群聊: {len(group_chats)} 个"
    )
    for index, person in enumerate(private_chats, 1):
        print(
            f"  {index}. 【{person['name']}】"
            f"({person['time_span']}): {person['total_count']}条"
        )

    analysis = analyze_and_reflect(private_chats, group_chats, date_str)
    push_success = push_to_feishu(build_feishu_card(analysis, total_all_groups))
    archive_to_obsidian(analysis)
    if push_success:
        print("🎉 任务执行成功，飞书卡片已推送，Obsidian 知识库已归档！")
    else:
        print("⚠️ 任务执行完成，但飞书推送异常，请检查网络或配置。")


if __name__ == "__main__":
    main()
