#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Native AGY Engine Bridge for Feishu Bot.
Executes prompts via local Google Antigravity language_server agentapi and reads results directly from AGY Brain transcript logs.
Zero external API key needed - pure native AGY intelligence!
"""

import os
import sys
import json
import time
import subprocess
import logging
from typing import Optional, Tuple

logger = logging.getLogger("AGYBridge")

try:
    from ..runtime import config
except ImportError:
    from core.runtime import config

IS_WSL = sys.platform != "win32" and os.path.exists("/mnt/c")
AGENTAPI_EXE = config.AGENTAPI_EXE
BRAIN_DIR = config.AGY_BRAIN_DIR

import re

def run_silent(cmd, **kwargs) -> subprocess.CompletedProcess:
    """Execute command silently with guaranteed zero console window popup on Windows."""
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)  # 0x08000000
        if "startupinfo" not in kwargs:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si
    return subprocess.run(cmd, **kwargs)

_CACHED_AGY_ENV: Optional[dict] = None

# Base environment variables required by Antigravity language_server agentapi
def get_live_agy_env(force_refresh: bool = False) -> dict:
    """
    Dynamically discover Language Server PID, CSRF token, and working agentapi port.
    Guarantees seamless connectivity across IDE restarts without hardcoded ports!
    Cached in memory to prevent unnecessary subprocess spawning and eliminate black windows.
    """
    global _CACHED_AGY_ENV
    if not force_refresh and _CACHED_AGY_ENV is not None:
        return _CACHED_AGY_ENV

    env = os.environ.copy()
    env.update({
        "ANTIGRAVITY_PROJECT_ID": "outside-of-project",
        "SYSTEMROOT": r"C:\Windows" if not IS_WSL else "",
        "WINDIR": r"C:\Windows" if not IS_WSL else "",
    })
    
    try:
        ps_cmd = "Get-CimInstance Win32_Process -Filter \"Name = 'language_server.exe' and CommandLine like '%--subclient_type hub%'\" | Select-Object ProcessId, CommandLine | Format-List"
        res = run_silent(["powershell", "-NoProfile", "-Command", ps_cmd], stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=10)
        m_pid = re.search(r"ProcessId\s*:\s*(\d+)", res.stdout)
        m_csrf = re.search(r"--csrf_token\s+([a-zA-Z0-9-]+)", res.stdout)
        if m_pid and m_csrf:
            proc_id = m_pid.group(1)
            csrf = m_csrf.group(1)
            
            port_cmd = f"(Get-NetTCPConnection -OwningProcess {proc_id} -State Listen).LocalPort"
            res_port = run_silent(["powershell", "-NoProfile", "-Command", port_cmd], stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=10)
            ports = [p.strip() for p in res_port.stdout.splitlines() if p.strip()]
            
            for port in ports:
                test_env = env.copy()
                test_env["ANTIGRAVITY_LS_ADDRESS"] = f"127.0.0.1:{port}"
                test_env["ANTIGRAVITY_CSRF_TOKEN"] = csrf
                
                # Verify port with conversation metadata (100% silent)
                test_res = run_silent(
                    [AGENTAPI_EXE, "agentapi", "get-conversation-metadata", config.AGY_CONVERSATION_ID],
                    env=test_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5
                )
                if test_res.returncode == 0 and "conversationMetadata" in test_res.stdout:
                    logger.info(f"🔌 自动探测到原生 AGY 活跃端口: {port} | CSRF 已就绪")
                    _CACHED_AGY_ENV = test_env
                    return test_env
    except Exception as e:
        logger.error(f"动态探测 AGY 端口异常: {e}")

    # Optional explicit fallback for environments where process discovery is unavailable.
    address = os.getenv("ANTIGRAVITY_LS_ADDRESS", "")
    csrf_token = os.getenv("ANTIGRAVITY_CSRF_TOKEN", "")
    if not address or not csrf_token:
        raise RuntimeError("无法发现 Antigravity 服务；请确认客户端已启动，或配置连接地址与临时令牌")
    env["ANTIGRAVITY_LS_ADDRESS"] = address
    env["ANTIGRAVITY_CSRF_TOKEN"] = csrf_token
    _CACHED_AGY_ENV = env
    return env

# Maintain session memory per Feishu user: open_id -> conversation_id
SESSIONS_FILE = os.path.join(str(config.PROJECT_ROOT), "data", "user_sessions.json")

def load_user_sessions() -> dict:
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_user_session(user_open_id: str, conv_id: str):
    sessions = load_user_sessions()
    sessions[user_open_id] = conv_id
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save user session: {e}")

USER_SESSIONS = load_user_sessions()

# Permanent Fixed Single Conversation ID for Feishu
FIXED_CONVERSATION_ID = config.AGY_CONVERSATION_ID

def get_latest_response_from_transcript(transcript_file: str, min_step: int = 0) -> Tuple[Optional[str], int]:
    """
    Parse transcript.jsonl and extract the latest finished user-facing PLANNER_RESPONSE.
    Excludes intermediate tool-calling steps to ensure the final answer is ready.
    Returns (content, step_index).
    """
    if not os.path.exists(transcript_file):
        return None, min_step
        
    latest_content = None
    latest_step = min_step
    
    try:
        with open(transcript_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                    
                step_idx = data.get("step_index", 0)
                msg_type = data.get("type")
                status = data.get("status")
                content = data.get("content")
                tool_calls = data.get("tool_calls")
                
                # Must be a completed PLANNER_RESPONSE with actual content and not in intermediate tool execution
                if msg_type == "PLANNER_RESPONSE" and status == "DONE" and content and not tool_calls and step_idx >= min_step:
                    latest_content = content
                    latest_step = step_idx
    except Exception as e:
        logger.error(f"Error reading transcript {transcript_file}: {e}")
        
    return latest_content, latest_step

def wait_for_agy_response(conv_id: str, start_step: int = 0, max_wait_sec: int = 600) -> str:
    """
    Streamingly listen to AGY Brain transcript until a finished user-facing PLANNER_RESPONSE appears.
    Zero premature timeouts - faithfully tracks the AI thinking process until complete.
    """
    transcript_file = os.path.join(BRAIN_DIR, conv_id, ".system_generated", "logs", "transcript.jsonl")
    start_time = time.time()
    
    logger.info(f"⏳ 正在流式监听 AGY 专属会话 ({conv_id}) 日志: 起始 step {start_step}...")
    
    poll_count = 0
    while time.time() - start_time < max_wait_sec:
        content, step = get_latest_response_from_transcript(transcript_file, min_step=start_step)
        if content and content.strip():
            # Wait brief moment to guarantee full content flush
            time.sleep(1.0)
            newer_content, _ = get_latest_response_from_transcript(transcript_file, min_step=step)
            final_ans = (newer_content or content).strip()
            logger.info(f"🎯 成功流式捕获 AGY 最终回答 (step: {step}, 耗时: {int(time.time() - start_time)}s)")
            return final_ans
            
        poll_count += 1
        if poll_count % 15 == 0:
            logger.info(f"⏳ 仍在流式持续监听 AGY 深度思考中... (已耗时 {int(time.time() - start_time)}s)")
            
        time.sleep(1.2)
        
    return "🤖 [AGY 认知引擎] 思考任务仍在进行中，请稍后在群中查看最新答复。"

FEISHU_FORMATTING_RULE = """【飞书移动端卡片专属排版铁律与安全约束】：
1. 严禁使用 Markdown 表格 (| 列1 | 列2 |)，飞书卡片不支持渲染表格；请统一使用 Emoji 结构化列表或键值对呈现。
2. 标题统一使用 **【一、xxx】** 或 **【二、xxx】** 加粗格式，不要使用容易溢出卡片的一级大标题 #。
3. 重点词汇请使用 **加粗** 或 `代码高亮`，适度空行，符合移动端阅读美学与呼吸感。
4. 语言精炼聚焦，突出核心要点与行动项，禁止空泛废话。
5. 【宿主网关保护铁律】：严禁在会话中执行杀掉或重启 feishu_bot_server.py 的命令（如 Stop-Process 等），必须保持宿主服务持续在线以正常回传消息！"""

def ask_native_agy(user_open_id: str, prompt: str, context: str = "") -> str:
    """
    Send prompt to local native AGY via agentapi using strictly FIXED_CONVERSATION_ID.
    Permanently locks 1 single conversation in IDE sidebar - 0 duplicate conversations!
    """
    conv_id = FIXED_CONVERSATION_ID
    if not AGENTAPI_EXE or not BRAIN_DIR or not conv_id:
        return "❌ AGY 未配置：请检查 AGENTAPI_EXE、AGY_BRAIN_DIR 与 AGY_CONVERSATION_ID。"
    
    # Compose full prompt with formatting rules
    prompt_parts = []
    if context:
        prompt_parts.append(f"【当前实时上下文与全局状态】：\n{context}")
    prompt_parts.append(FEISHU_FORMATTING_RULE)
    prompt_parts.append(f"【用户指令/提问】：\n{prompt}")
    full_prompt = "\n\n".join(prompt_parts)
    
    transcript_file = os.path.join(BRAIN_DIR, conv_id, ".system_generated", "logs", "transcript.jsonl")
    _, highest_step = get_latest_response_from_transcript(transcript_file, min_step=0)
    
    try:
        logger.info(f"🔄 正在向唯一永久会话 ({conv_id}) 发送新指令 (起始 step: {highest_step + 1})...")
        cmd = [AGENTAPI_EXE, "agentapi", "send-message", conv_id, full_prompt]
        
        live_env = get_live_agy_env()
        res = run_silent(
            cmd, 
            env=live_env, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            encoding="utf-8", 
            errors="replace", 
            timeout=25
        )
        
        if res.returncode != 0:
            err_msg = (res.stderr or "").strip() or (res.stdout or "").strip() or f"退出码: {res.returncode}"
            # If port changed / connection refused, invalidate cache and retry once silently
            if any(k in err_msg for k in ["Unavailable", "connectex", "connection error"]):
                logger.warning("⚠️ 检测到连接失效，尝试刷新动态端口与令牌重试...")
                live_env = get_live_agy_env(force_refresh=True)
                res = run_silent(
                    cmd,
                    env=live_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=25
                )
                if res.returncode == 0:
                    err_msg = ""
            if res.returncode != 0:
                logger.error(f"调用 agentapi send-message 失败! rc={res.returncode}, err={err_msg}")
                return f"❌ 提交思考任务失败: {err_msg}"
            
        # Streamingly wait for the final response without premature timeouts
        answer = wait_for_agy_response(conv_id, start_step=highest_step + 1)
        return answer
        
    except Exception as e:
        logger.error(f"调用 AGY Bridge 发生异常: {e}", exc_info=True)
        return f"❌ AGY 智能体交互异常: {str(e)}"

if __name__ == "__main__":
    test_ans = ask_native_agy("test_user", "你好，请确认你是否是原生 AGY 智能体？")
    print("Test Answer:", test_ans)
