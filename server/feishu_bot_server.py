#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AGY Full-Capability Feishu Bidirectional Agent Server
Runs in WSL / Windows background via systemd daemon.
Integrated with Native Google Antigravity (AGY) agentapi cognitive engine + local Obsidian knowledge RAG + Feishu Calendar management.
Acts as a true, intelligent AGY assistant in Feishu instead of static replies!
"""

import os
import sys
import io
import json
import re
import time
import datetime
import logging
import threading
from logging.handlers import RotatingFileHandler
import ctypes
from typing import Dict, Any, List, Optional

# Bypass local proxies for domestic Feishu endpoints (prevents SSLEOFError from local VPN/Clash proxies)
for p_var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(p_var, None)
os.environ["NO_PROXY"] = "open.feishu.cn,msg-frontier.feishu.cn,feishu.cn"

# If running on Windows with an active console window, hide it completely into background
if sys.platform == "win32":
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        user32 = ctypes.WinDLL("user32")
        hWnd = kernel32.GetConsoleWindow()
        if hWnd:
            user32.ShowWindow(hWnd, 0)  # SW_HIDE
    except Exception:
        pass

# Resolve the checkout location instead of binding the server to one computer.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "feishu_bot.log")
IMAGE_DIR = os.path.join(PROJECT_ROOT, "received_images")
os.makedirs(IMAGE_DIR, exist_ok=True)

# Ensure stdout/stderr are valid streams (crucial for pythonw.exe & silent daemon)
WINDOWLESS = sys.stdout is None
if WINDOWLESS:
    sys.stdout = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
elif hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if sys.stderr is None:
    sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
elif hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.runtime.observability import SensitiveDataFilter

log_filter = SensitiveDataFilter()
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.addFilter(log_filter)
handlers = [file_handler]
if not WINDOWLESS:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.addFilter(log_filter)
    handlers.append(stream_handler)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=handlers,
    force=True,
)
logger = logging.getLogger("AGYFeishuBot")

DATA_DIR = os.path.join(PROJECT_ROOT, "data")

import lark_oapi as lark
from lark_oapi.ws import Client as WsClient
from lark_oapi.api.im.v1 import *
from concurrent.futures import ThreadPoolExecutor
from collections import deque

from core.runtime import config
from core.integrations.feishu import calendar as feishu_calendar
from core.agent import agy_bridge
from core.agent import provider as agent_provider
from services.planning import daily_todo as daily_todo_service
from services.lifestyle import feishu_archive
from core.agent import context as agent_context
from core.integrations.feishu.gateway import feishu_gateway
from core.runtime.observability import event, traced
from .replies import (
    build_reply_card as _build_reply_card,
    download_feishu_image as _download_feishu_image,
    reply_feishu_message as _reply_feishu_message,
    update_feishu_reply as _update_feishu_reply,
)
from . import message_processor, progress
from storage.facts import record_lifestyle_fact
from services.lifestyle.nutrition_analysis import estimate_meal
from services.lifestyle.nutrition_analysis import handle_confirmation

VAULT_ROOT = config.VAULT_ROOT

# Thread pool for asynchronous event handling (keeps WebSocket loop unblocked)
WORKER_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="AGYWorker")

# Message deduplication cache: keeps recent 2000 message IDs
PROCESSED_MSG_IDS = set()
PROCESSED_MSG_QUEUE = deque(maxlen=2000)

def download_feishu_image(message_id: str, image_key: str) -> Optional[str]:
    return _download_feishu_image(feishu_gateway, IMAGE_DIR, message_id, image_key)

# User recent image buffer: user_open_id -> list of {"path": str, "time": float, "msg_id": str}
USER_IMAGE_BUFFERS: Dict[str, List[Dict[str, Any]]] = {}
BUFFER_TTL_SECONDS = 300  # 5 minutes window

def add_user_image(sender_open_id: str, img_path: str, msg_id: str):
    """Add downloaded image to user's sliding buffer."""
    now = time.time()
    buf = USER_IMAGE_BUFFERS.get(sender_open_id, [])
    # Filter expired items
    buf = [item for item in buf if now - item["time"] < BUFFER_TTL_SECONDS]
    buf.append({"path": img_path, "time": now, "msg_id": msg_id})
    USER_IMAGE_BUFFERS[sender_open_id] = buf[-5:]  # Keep at most 5 recent images
    logger.info(f"📥 [多模态缓冲更新] 用户 {sender_open_id} 缓冲区当前保有 {len(USER_IMAGE_BUFFERS[sender_open_id])} 张图片")

def get_and_clear_user_images(sender_open_id: str) -> List[str]:
    """Retrieve all valid images in buffer and clear them."""
    now = time.time()
    buf = USER_IMAGE_BUFFERS.get(sender_open_id, [])
    valid = [item["path"] for item in buf if now - item["time"] < BUFFER_TTL_SECONDS]
    USER_IMAGE_BUFFERS[sender_open_id] = []
    return valid

def build_reply_card(content: str, title: str = "🤖 AGY 智能协同助手", template: str = "blue") -> dict:
    return _build_reply_card(content, title, template)

def reply_feishu_message(message_id: str, reply_text: str, title: str = "🤖 AGY 智能协同助手", template: str = "blue"):
    return _reply_feishu_message(
        feishu_gateway, message_id, reply_text, title, template
    )

def update_feishu_reply(message_id: str, reply_text: str, title: str = "🤖 AGY 智能协同助手", template: str = "blue"):
    return _update_feishu_reply(
        feishu_gateway, message_id, reply_text, title, template
    )

def animate_thinking_reply(
    reply_message_id: str,
    stop_event: threading.Event,
) -> None:
    progress.animate(
        reply_message_id, stop_event, update_feishu_reply, logger=logger
    )


def stop_thinking_animation(
    stop_event: Optional[threading.Event],
    animation_thread: Optional[threading.Thread],
) -> None:
    progress.stop(stop_event, animation_thread)


def gather_agent_context(query: str) -> str:
    """Collect only user-configured context; never assume a personal domain."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context = agent_context.collect_context(query)
    return f"【当前时间】\n{now}\n\n{context or '没有配置本地知识库上下文。'}"


def ask_agent_for_message(
    sender_open_id: str,
    prompt: str,
    context: str = "",
) -> str:
    """Use the shared provider boundary so conversation usage is recorded."""
    return agent_provider.ask_text("feishu-conversation", prompt, context)

@traced(logger, "server.process_message")
def process_message_async(sender_open_id: str, user_text: str, msg_id: str):
    """Worker task executed in thread pool to prevent blocking WebSocket loop."""
    message_processor.process_message(
        sender_open_id,
        user_text,
        msg_id,
        todo_handler=daily_todo_service.handle_todo_intent,
        get_images=get_and_clear_user_images,
        archive_lifestyle=feishu_archive.archive_lifestyle_message,
        reply=reply_feishu_message,
        update=update_feishu_reply,
        gather_context=gather_agent_context,
        ask_agent=ask_agent_for_message,
        record_fact=record_lifestyle_fact,
        estimate_meal=estimate_meal,
        confirm_lifestyle=handle_confirmation,
        animate=animate_thinking_reply,
        stop_animation=stop_thinking_animation,
        event_fn=event,
        logger=logger,
    )

def extract_feishu_user_text(content_raw: str) -> str:
    """Extract plain text from Feishu message whether text, post (rich text), or json."""
    try:
        content_obj = json.loads(content_raw)
    except Exception:
        return content_raw.strip()
        
    if isinstance(content_obj, dict):
        if "text" in content_obj:
            return content_obj.get("text", "").strip()
        if "content" in content_obj:
            # Feishu post structure: {"title": "", "content": [[{"tag": "text", "text": "..."}]]}
            parts = []
            title = content_obj.get("title", "")
            if title:
                parts.append(title)
            for para in content_obj.get("content", []):
                if isinstance(para, list):
                    parts.append("".join([
                        elem.get("text", "") 
                        for elem in para 
                        if isinstance(elem, dict) and elem.get("tag") in ["text", "a", "at"]
                    ]))
                elif isinstance(para, str):
                    parts.append(para)
            return "\n".join(parts).strip()
    elif isinstance(content_obj, str):
        return content_obj.strip()
    return ""

def on_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    """Handle incoming message event from Feishu client (non-blocking + deduplicated + multimodal)."""
    try:
        msg = data.event.message
        sender = data.event.sender
        msg_id = msg.message_id
        sender_open_id = sender.sender_id.open_id
        msg_type = getattr(msg, "message_type", "text")

        if sender_open_id not in config.FEISHU_ALLOWED_OPEN_IDS:
            logger.warning("⛔ 已拒绝未授权的飞书发送者")
            return
        
        # Deduplication check: prevent multiple execution from WebSocket retry/reconnect pushes
        if msg_id in PROCESSED_MSG_IDS:
            logger.info(f"⏭️ [忽略重复推送消息] MsgID 已处理过: {msg_id}")
            return
            
        if len(PROCESSED_MSG_QUEUE) == PROCESSED_MSG_QUEUE.maxlen:
            oldest = PROCESSED_MSG_QUEUE.popleft()
            PROCESSED_MSG_IDS.discard(oldest)
        PROCESSED_MSG_IDS.add(msg_id)
        PROCESSED_MSG_QUEUE.append(msg_id)

        # 1. Handle pure image message
        if msg_type == "image":
            logger.info(f"📸 [收到飞书图片消息] 来自: {sender_open_id} | MsgID: {msg_id}")
            img_key = ""
            try:
                content_obj = json.loads(msg.content)
                img_key = content_obj.get("image_key", "")
            except Exception:
                pass
                
            if img_key:
                saved_path = download_feishu_image(msg_id, img_key)
                if saved_path:
                    add_user_image(sender_open_id, saved_path, msg_id)
                    card_content = (
                        "📸 **已成功接收并解析您的图片！**\n\n"
                        "• 本地视界归档就绪，多模态认知引擎已挂载\n"
                        "• 您可以继续发送指令（如*“这是今天早上的饭，帮我点评营养”*或*“帮我解答这道题”*），我将调阅图片为您深度研判！"
                    )
                    reply_feishu_message(msg_id, card_content, title="📸 图片已接收", template="turquoise")
            return

        # 2. Check if post contains images
        if msg_type == "post":
            try:
                content_obj = json.loads(msg.content)
                for para in content_obj.get("content", []):
                    if isinstance(para, list):
                        for elem in para:
                            if isinstance(elem, dict) and elem.get("tag") == "img" and elem.get("image_key"):
                                p_img = download_feishu_image(msg_id, elem.get("image_key"))
                                if p_img:
                                    add_user_image(sender_open_id, p_img, msg_id)
            except Exception as e:
                logger.warning(f"解析富文本图片异常: {e}")
            
        # Parse content (supports both text and post rich-text)
        user_text = extract_feishu_user_text(msg.content)
        
        # Strip @mention tags if in group
        if "@_user" in user_text:
            user_text = re.sub(r"@_user_\d+", "", user_text).strip()
            
        logger.info(f"📩 [收到飞书新消息] MsgID: {msg_id} | 类型: {msg_type} | 字符数: {len(user_text)}")
        
        if not user_text:
            return
            
        # Dispatch to worker pool asynchronously so WebSocket handler returns instantly (ACK)
        WORKER_POOL.submit(process_message_async, sender_open_id, user_text, msg_id)
        
    except Exception as e:
        logger.error(f"❌ 消息事件分发异常: {e}", exc_info=True)

def run_server():
    """Start WebSocket Long Connection Client in daemon mode."""
    missing = [
        name for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_ALLOWED_OPEN_IDS")
        if not getattr(config, name)
    ]
    if missing:
        raise RuntimeError(f"缺少必要配置: {', '.join(missing)}")
    logger.info("=" * 60)
    logger.info("  🚀 AGY 原生智能体双向实时对话服务启动 (WSL / systemd)")
    logger.info("=" * 60)
    logger.info(f"🔑 App ID: {config.FEISHU_APP_ID}")
    logger.info(f"📂 知识库路径: {VAULT_ROOT}")
    logger.info(f"🧠 大脑引擎: 原生 Google Antigravity (language_server.exe agentapi)")
    logger.info("📡 正在连接飞书开放平台 WebSocket 事件通道...")
    
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_p2_im_message_receive_v1) \
        .build()
        
    ws_client = WsClient(
        app_id=config.FEISHU_APP_ID,
        app_secret=config.FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.WARNING
    )
    
    logger.info("✅ 飞书 WebSocket 长连接网关已就绪！原生 AGY 智能体全面待命。")
    ws_client.start()


def start_bot():
    """Stable public entry point used by the CLI."""
    return run_server()


if __name__ == "__main__":
    run_server()
