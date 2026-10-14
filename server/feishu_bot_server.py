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
import urllib.request
import logging
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
if sys.stdout is None:
    sys.stdout = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
elif hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if sys.stderr is None:
    sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
elif hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler(sys.stdout)]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=handlers
)
logger = logging.getLogger("AGYFeishuBot")

# Ensure project root, core, and services are in sys.path
CORE_DIR = os.path.join(PROJECT_ROOT, "core")
SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
for p in [PROJECT_ROOT, CORE_DIR, SERVICES_DIR, DATA_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

import lark_oapi as lark
from lark_oapi.ws import Client as WsClient
from lark_oapi.api.im.v1 import *
from concurrent.futures import ThreadPoolExecutor
from collections import deque

import config
import feishu_calendar
import agy_bridge
import daily_todo_service
import agent_context

VAULT_ROOT = config.VAULT_ROOT

# Thread pool for asynchronous event handling (keeps WebSocket loop unblocked)
WORKER_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="AGYWorker")

# Message deduplication cache: keeps recent 2000 message IDs
PROCESSED_MSG_IDS = set()
PROCESSED_MSG_QUEUE = deque(maxlen=2000)

def get_tenant_token() -> str:
    """Fetch Feishu tenant token for sending messages."""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = json.dumps({"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json; charset=utf-8"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("tenant_access_token", "")
    except Exception as e:
        logger.error(f"获取 Feishu Token 异常: {e}")
        return ""

def download_feishu_image(message_id: str, image_key: str) -> Optional[str]:
    """Download image binary from Feishu Open API and save locally."""
    token = get_tenant_token()
    if not token:
        logger.error("Token 为空，无法下载飞书图片")
        return None
        
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{image_key}?type=image"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_key = re.sub(r'[^a-zA-Z0-9_-]', '_', image_key[-16:])
    filename = f"{timestamp_str}_{message_id[-8:]}_{safe_key}.jpg"
    filepath = os.path.join(IMAGE_DIR, filename)
    
    try:
        with opener.open(req, timeout=20) as resp:
            data = resp.read()
            with open(filepath, "wb") as f:
                f.write(data)
            logger.info(f"📸 [飞书图片下载成功] 已存至: {filepath} (大小: {len(data)} 字节)")
            return filepath
    except Exception as e:
        logger.error(f"❌ 下载飞书图片失败 (MsgID: {message_id}, key: {image_key}): {e}")
        return None

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
    """Build a high-aesthetic Feishu Interactive Card for replies."""
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    return {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "template": template,
            "title": {
                "tag": "plain_text",
                "content": title
            }
        },
        "elements": [
            {
                "tag": "markdown",
                "content": content.strip()
            },
            {
                "tag": "hr"
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"Google Antigravity 原生引擎 · 回复时戳 {now_str}"
                    }
                ]
            }
        ]
    }

def reply_feishu_message(message_id: str, reply_text: str, title: str = "🤖 AGY 智能协同助手", template: str = "blue"):
    """Reply to a message in Feishu thread using high-aesthetic Interactive Card."""
    token = get_tenant_token()
    if not token:
        logger.error("Token 为空，无法回复消息")
        return
        
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    
    # 1. Primary: Send Interactive Card
    card_obj = build_reply_card(reply_text, title=title, template=template)
    body = {
        "content": json.dumps(card_obj, ensure_ascii=False),
        "msg_type": "interactive"
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
    )
    try:
        with opener.open(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("code") == 0:
                logger.info(f"✅ 成功向飞书回复精美交互卡片 (MsgID: {message_id})")
                return
            else:
                logger.warning(f"⚠️ 卡片回复响应异常 (code={res.get('code')}, msg={res.get('msg')})，尝试降级纯文本...")
    except Exception as e:
        logger.warning(f"⚠️ 卡片回复网络失败: {e}，尝试降级纯文本...")

    # 2. Fallback: Plain text fallback to guarantee message delivery
    try:
        fb_body = {
            "content": json.dumps({"text": reply_text}, ensure_ascii=False),
            "msg_type": "text"
        }
        fb_req = urllib.request.Request(
            url,
            data=json.dumps(fb_body).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        )
        with opener.open(fb_req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("code") == 0:
                logger.info(f"✅ 纯文本降级回复成功 (MsgID: {message_id})")
            else:
                logger.error(f"❌ 降级回复失败: {res.get('msg')}")
    except Exception as ex:
        logger.error(f"❌ 回复飞书消息彻底失败: {ex}")

def gather_agent_context(query: str) -> str:
    """Collect only user-configured context; never assume a personal domain."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context = agent_context.collect_context(query)
    return f"【当前时间】\n{now}\n\n{context or '没有配置本地知识库上下文。'}"

def process_message_async(sender_open_id: str, user_text: str, msg_id: str):
    """Worker task executed in thread pool to prevent blocking WebSocket loop."""
    try:
        # 1. Fast-track todo command & evening review confirmation
        todo_reply = daily_todo_service.handle_todo_intent(user_text)
        if todo_reply:
            logger.info(f"⚡ [待办意图快速拦截命中] 立即响应待办指令: {user_text}")
            reply_feishu_message(msg_id, todo_reply, title="📋 待办事项实时处理", template="indigo")
            return

        # 2. Check for attached / recently buffered images for multimodal visual cognition
        attached_images = get_and_clear_user_images(sender_open_id)
        if attached_images:
            img_bullets = "\n".join([f"- file:///{p.replace(os.sep, '/')}" for p in attached_images])
            user_text = (
                f"{user_text}\n\n"
                f"【用户发送的多模态图片附件】：\n"
                f"{img_bullets}\n"
                f"⚠️ 请务必使用 view_file 工具直接打开并查看上述本地图片文件，进行深入的多模态视觉识别与理解，结合图片中的真实细节（如餐食搭配、食材、文字、图表等）为用户提供专业细致的解答！"
            )
            logger.info(f"🖼️ [多模态视觉上下文挂载] 成功关联 {len(attached_images)} 张图片至认知推理")

        # 3. Immediately notify user with thinking status card (Zero waiting anxiety)
        reply_feishu_message(
            msg_id, 
            "⏳ **正在分析你的问题与已配置的本地知识库，回复生成中...**\n• 本地智能体推理中\n• 仅使用当前请求与授权上下文",
            title="🤖 AGY 智能协同助手 (思考中...)", 
            template="turquoise"
        )

        # 4. Gather live context
        context = gather_agent_context(user_text)
        
        # 5. Call Native Google Antigravity (AGY) Engine with streaming listener
        logger.info(f"🧠 [原生 AGY 认知引擎激活] 正在执行原生流式推理 (MsgID: {msg_id})...")
        reply_text = agy_bridge.ask_native_agy(sender_open_id, user_text, context)
        logger.info(f"📤 [AGY 原生回答就绪] {reply_text[:100]}...")
        
        # 6. Deliver final high-aesthetic response card back to Feishu
        reply_feishu_message(msg_id, reply_text, title="🤖 AGY 智能协同助手", template="blue")
    except Exception as e:
        logger.error(f"❌ 异步处理消息任务异常 (MsgID: {msg_id}): {e}", exc_info=True)

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
        log_level=lark.LogLevel.INFO
    )
    
    logger.info("✅ 飞书 WebSocket 长连接网关已就绪！原生 AGY 智能体全面待命。")
    ws_client.start()

if __name__ == "__main__":
    run_server()
