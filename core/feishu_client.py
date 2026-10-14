#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Feishu OpenAPI Communication Client (爪爪openclaw)
All cards, messages, tasks, and notifications are sent strictly through official OpenAPI,
completely replacing legacy one-way Webhooks. Every message can be directly replied to!
"""

import os
import sys
import json
import time
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("FeishuClient")

try:
    from . import config
except ImportError:
    import config

class FeishuClient:
    """Official Feishu OpenAPI Client (爪爪openclaw)."""

    def __init__(self):
        self.app_id = getattr(config, "FEISHU_APP_ID", "")
        self.app_secret = getattr(config, "FEISHU_APP_SECRET", "")
        self.chat_id = getattr(config, "FEISHU_CHAT_ID", "")
        self.user_open_id = getattr(config, "FEISHU_USER_OPEN_ID", "")
        self._token = None
        self._token_expire = 0
        self.session = requests.Session()

    def get_token(self) -> Optional[str]:
        """Fetch or refresh tenant access token."""
        now = time.time()
        if self._token and now < self._token_expire - 60:
            return self._token

        if not self.app_id or not self.app_secret:
            logger.error("Missing FEISHU_APP_ID or FEISHU_APP_SECRET")
            return None

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        try:
            r = self.session.post(url, json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=10)
            res = r.json()
            if res.get("code") == 0:
                self._token = res.get("tenant_access_token")
                self._token_expire = now + res.get("expire", 7200)
                return self._token
            else:
                logger.error(f"Failed to fetch tenant token: {res.get('msg')}")
        except Exception as e:
            logger.error(f"Network error fetching tenant token: {e}")
        return None

    def send_card(self, card: dict, chat_id: Optional[str] = None, user_open_id: Optional[str] = None) -> bool:
        """
        Send an interactive card directly via 爪爪openclaw OpenAPI.
        Defaults to configured group chat_id.
        """
        token = self.get_token()
        if not token:
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        # Determine target
        if chat_id:
            receive_type = "chat_id"
            target_id = chat_id
        elif user_open_id:
            receive_type = "open_id"
            target_id = user_open_id
        elif self.chat_id:
            receive_type = "chat_id"
            target_id = self.chat_id
        elif self.user_open_id:
            receive_type = "open_id"
            target_id = self.user_open_id
        else:
            logger.error("Missing FEISHU_CHAT_ID or FEISHU_USER_OPEN_ID")
            return False

        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_type}"
        # If caller passed {'msg_type': 'interactive', 'card': {...}}, extract inner card
        card_content = card.get("card", card) if isinstance(card, dict) else card

        payload = {
            "receive_id": target_id,
            "msg_type": "interactive",
            "content": json.dumps(card_content, ensure_ascii=False)
        }

        try:
            r = self.session.post(url, headers=headers, json=payload, timeout=12)
            res = r.json()
            if res.get("code") == 0:
                msg_id = res.get("data", {}).get("message_id")
                logger.info(f"✅ 爪爪openclaw 卡片发送成功! Target: {target_id} | MsgID: {msg_id}")
                return True
            else:
                logger.warning(f"⚠️ 爪爪openclaw 发送卡片响应异常: code={res.get('code')}, msg={res.get('msg')}")
        except Exception as e:
            logger.error(f"❌ 爪爪openclaw 发送卡片网络异常: {e}")

        # Fallback to user private chat if group chat fails
        if receive_type == "chat_id" and self.user_open_id and self.user_open_id != target_id:
            try:
                fb_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
                fb_payload = {
                    "receive_id": self.user_open_id,
                    "msg_type": "interactive",
                    "content": json.dumps(card, ensure_ascii=False)
                }
                r2 = self.session.post(fb_url, headers=headers, json=fb_payload, timeout=10)
                if r2.json().get("code") == 0:
                    logger.info("✅ 爪爪openclaw 私聊回退兜底发送成功!")
                    return True
            except Exception:
                pass

        return False

    def send_text(self, text: str, chat_id: Optional[str] = None, user_open_id: Optional[str] = None) -> bool:
        """Send plain text message directly via 爪爪openclaw OpenAPI."""
        token = self.get_token()
        if not token:
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        if chat_id:
            receive_type = "chat_id"
            target_id = chat_id
        elif user_open_id:
            receive_type = "open_id"
            target_id = user_open_id
        elif self.chat_id:
            receive_type = "chat_id"
            target_id = self.chat_id
        elif self.user_open_id:
            receive_type = "open_id"
            target_id = self.user_open_id
        else:
            logger.error("Missing FEISHU_CHAT_ID or FEISHU_USER_OPEN_ID")
            return False

        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_type}"
        payload = {
            "receive_id": target_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False)
        }

        try:
            r = self.session.post(url, headers=headers, json=payload, timeout=10)
            res = r.json()
            return res.get("code") == 0
        except Exception as e:
            logger.error(f"❌ 爪爪openclaw 发送文本消息失败: {e}")
            return False

# Global singleton client
feishu_client = FeishuClient()
