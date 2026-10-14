#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Todo & Schedule Service (Unified Planning & Evening Review Agent)
1. Evening review: Scans configured chat logs, prepares Agent-generated Todos + Calendar Schedule Slots, sends a unified review card to Feishu.
2. Evening Interaction: User can adjust schedule times ("健身改到六点") or add todos ("加上xxx") or confirm ("确认/没问题").
3. Morning 06:00: Archives yesterday's plan, writes today's Obsidian 今日待办.md, creates Feishu official tasks (Task v2),
   and writes schedule events directly to Feishu Calendar (with 15-min advance alarms).
4. 24/7 Realtime: Supports adding custom todos anytime via Feishu message ("加待办: xxx").
"""

import os
import sys
import io
import json
import re
import sqlite3
import datetime
import subprocess
import requests
from typing import List, Dict, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
CORE_DIR = os.path.join(PROJECT_ROOT, "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

import config
import agent_context
import agy_bridge
import feishu_calendar
from feishu_client import feishu_client

SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
if SERVICES_DIR not in sys.path:
    sys.path.insert(0, SERVICES_DIR)

import review_sync_service

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
STAGED_PLAN_FILE = os.path.join(DATA_DIR, "staged_plan.json")
if not os.path.exists(STAGED_PLAN_FILE) and os.path.exists(os.path.join(PROJECT_ROOT, "staged_plan.json")):
    STAGED_PLAN_FILE = os.path.join(PROJECT_ROOT, "staged_plan.json")

ARCHIVE_DIR = os.path.join(config.VAULT_ROOT, "03 - 待办事项", "历史归档")

WECHAT_TOOLS_DIR = config.WECHAT_TOOLS_DIR
DECRYPT_SCRIPT = os.path.join(WECHAT_TOOLS_DIR, "decrypt_db.py")
WECHAT_MSG_DB = config.WECHAT_MSG_DB
WECHAT_CONTACT_DB = config.WECHAT_CONTACT_DB
FEISHU_BOT_LOG = os.path.join(PROJECT_ROOT, "logs", "feishu_bot.log")

def sync_wechat_database() -> bool:
    """Run local decrypt script to ensure WeChat databases are up-to-date."""
    if not os.path.exists(DECRYPT_SCRIPT):
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
            timeout=30,
            **sub_kwargs
        )
        return res.returncode == 0
    except Exception:
        return False

# --- 1. Agent-generated plan inputs ---
def get_default_baseline_todos() -> List[str]:
    """Return no personal defaults; the local agent supplies the plan."""
    return []

# --- 2. Schedule slots are supplied by the agent or staged plan ---
def get_default_schedule_slots(target_date: datetime.date) -> List[Dict[str, str]]:
    return []


def generate_agent_plan(target_date: str) -> Dict[str, Any]:
    """Ask the local agent for a JSON plan based on the configured context."""
    prompt = agent_context.build_prompt(
        task=(
            "为指定日期生成一个可执行计划，只能使用本地资料中明确存在的目标和约束。"
            "输出严格 JSON：{\"todos\": [\"...\"], \"schedule_slots\": "
            "[{\"name\":\"...\",\"start\":\"HH:MM\",\"end\":\"HH:MM\","
            "\"summary\":\"...\",\"desc\":\"...\"}]}。资料不足时返回空数组，"
            "不要自行发明学习、运动、工作或生活目标。"
        ),
        query=f"请为 {target_date} 生成计划。",
    )
    try:
        result = agy_bridge.ask_native_agy("daily-plan", prompt)
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", result, re.DOTALL)
        raw = fenced.group(1) if fenced else result
        data = json.loads(raw)
        if isinstance(data, dict):
            data.setdefault("todos", [])
            data.setdefault("schedule_slots", [])
            data["date"] = target_date
            return data
    except Exception as exc:
        print(f"Agent plan unavailable: {exc}")
    return {"date": target_date, "todos": [], "schedule_slots": []}

# --- 3. Staged Plan Helper ---
def load_staged_plan() -> Dict[str, Any]:
    if os.path.exists(STAGED_PLAN_FILE):
        try:
            with open(STAGED_PLAN_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_staged_plan(data: Dict[str, Any]):
    try:
        with open(STAGED_PLAN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving staged plan: {e}")

# --- 4. Extract Candidates from WeChat/Feishu Chat Logs ---
# --- 4. Extract Candidates from WeChat/Feishu Chat Logs & Unfinished Todos ---
def extract_candidates_from_chat() -> List[str]:
    """Extract candidate action items from WeChat decrypted messages, Feishu bot logs, and today's unfinished todos."""
    candidates = []
    seen = set()

    # 1. First automatically sync latest WeChat database to capture evening messages
    try:
        sync_wechat_database()
    except Exception as se:
        print(f"Sync WeChat db before extract warning: {se}")

    today_start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = int(today_start.timestamp())

    # 2. Extract from WeChat messages (both personal and group discussions)
    if os.path.exists(WECHAT_MSG_DB):
        try:
            conn = sqlite3.connect(WECHAT_MSG_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%';")
            tables = [r[0] for r in cursor.fetchall()]

            keywords = ["记得", "需要", "明天要", "待办", "处理一下", "安排", "改一下", "改下", "查一下", "确认下", "发一下", "买", "修复", "更新", "跟进", "测试"]

            for t in tables:
                try:
                    cursor.execute(f"SELECT message_content, create_time, status FROM {t} WHERE create_time >= ? ORDER BY create_time DESC LIMIT 25;", (today_ts,))
                    rows = cursor.fetchall()
                    for content, c_time, status in rows:
                        if not content or not isinstance(content, str):
                            continue
                        content = content.strip()
                        if len(content) < 4 or len(content) > 80:
                            continue
                        if ":\n" in content[:30]:
                            content = content.split(":\n", 1)[1].strip()
                        if content.startswith("<?xml") or content.startswith("<msg>") or "<appmsg" in content or content.startswith("http"):
                            continue
                        has_kw = any(kw in content for kw in keywords)
                        if has_kw and content not in seen:
                            seen.add(content)
                            candidates.append(content)
                            if len(candidates) >= 5:
                                break
                except Exception:
                    continue
                if len(candidates) >= 5:
                    break
            conn.close()
        except Exception as e:
            print(f"WeChat scan exception: {e}")

    # 3. Extract from Feishu Bot Logs of today
    if os.path.exists(FEISHU_BOT_LOG):
        try:
            with open(FEISHU_BOT_LOG, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "收到飞书新消息" in line and "内容: '" in line:
                        m = re.search(r"内容:\s*'([^']+)'", line)
                        if m:
                            text = m.group(1).strip()
                            if any(k in text for k in ["改", "换成", "加", "明天", "备忘", "待办", "计划", "做"]):
                                if text not in seen and len(text) < 50:
                                    seen.add(text)
                                    candidates.append(text)
        except Exception as fe:
            print(f"Feishu log scan warning: {fe}")

    # 4. Extract unfinished todos from 今日待办.md to rollover
    if os.path.exists(config.TODAY_TODO_PATH):
        try:
            with open(config.TODAY_TODO_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line_s = line.strip()
                    if line_s.startswith("- [ ]") and "**" in line_s:
                        m_todo = re.search(r"\*\*(.*?)\*\*", line_s)
                        if m_todo:
                            item = m_todo.group(1).strip()
                            if item not in seen:
                                seen.add(item)
                                candidates.append(f"【顺延未完】{item}")
        except Exception as te:
            print(f"Todo rollover scan warning: {te}")

    return candidates[:6]

# --- 5. Send Unified Evening Review Prompt ---
def send_evening_review_prompt() -> bool:
    """Send a review card for Agent-generated todos and schedule slots."""
    now = datetime.datetime.now()
    tomorrow_date = (now + datetime.timedelta(days=1)).date()
    tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")
    weekday_str = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][tomorrow_date.weekday()]

    candidates = extract_candidates_from_chat()
    baseline_todos = get_default_baseline_todos()

    # Merge candidates into todos if any
    all_todos = list(baseline_todos)
    for c in candidates:
        if c not in all_todos:
            all_todos.append(c)

    default_slots = get_default_schedule_slots(tomorrow_date)

    # Save to staged plan
    plan_data = {
        "date": tomorrow_str,
        "weekday": weekday_str,
        "todos": all_todos,
        "schedule_slots": default_slots,
        "candidates": candidates,
        "confirmed": False
    }
    save_staged_plan(plan_data)

    # Build prompt card lark_md content
    todo_text = "📋 **【明日核心待办预排】**\n"
    for i, t in enumerate(all_todos, 1):
        is_cand = t in candidates
        tag = " *(沟通提炼)*" if is_cand else ""
        todo_text += f"• [ ] **{t}**{tag}\n"

    slot_text = "⏱️ **【明日作息日程预排】**\n"
    for s in default_slots:
        slot_text += f"• **{s['name']}**：`{s['start']} ~ {s['end']}` ({s['summary'].split('：')[-1]})\n"

    prompt_body = (
        f"晚上好！🌙 正在为你预排 **{tomorrow_str} ({weekday_str})** 的待办与日程：\n\n"
        f"{todo_text}\n"
        f"{slot_text}\n"
        "❓ **以上待办与时间盒排期是否合适？**\n\n"
        "💬 *如需调整时间或事项，可直接在飞书回复：*\n"
        "• “**把某个时间块改到 18:00**”\n"
        "• “**加上：明天要处理一件事**”\n"
        "• “**没问题**” / “**确认**” ➔ 锁定排期，明早 06:00 正式写入飞书日历与任务列表！"
    )

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"🌙 明日待办与日程综合预审 ({tomorrow_str})"},
            "template": "indigo"
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": prompt_body}
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "🤖 Agent 统合预审 | 确认后写入本地归档、任务与日历"}
                ]
            }
        ]
    }

def get_weekly_archive_dir(archive_base: str, date_str: str) -> str:
    """计算指定日期所属自然周 (周一至周日) 的周目录名，如 2026-W42 (10.12 - 10.18)"""
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        dt = datetime.date.today()
    year, week, weekday = dt.isocalendar()
    monday = dt - datetime.timedelta(days=weekday - 1)
    sunday = monday + datetime.timedelta(days=6)
    folder_name = f"{year}-W{week:02d} ({monday.strftime('%m.%d')} - {sunday.strftime('%m.%d')})"
    target_dir = os.path.join(archive_base, folder_name)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


# --- 6. Generate and Publish Morning Todo (06:00) ---
def generate_and_publish_morning_todo() -> bool:
    """Generate today's Obsidian 今日待办.md, create Feishu Tasks and Feishu Calendar events at 06:00."""
    now = datetime.datetime.now()
    today_date = now.date()
    today_str = today_date.strftime("%Y-%m-%d")
    weekday_str = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][today_date.weekday()]

    # 1. Archive yesterday's 今日待办.md into weekly folder
    if os.path.exists(config.TODAY_TODO_PATH):

        try:
            with open(config.TODAY_TODO_PATH, "r", encoding="utf-8") as f:
                old_content = f.read()
            old_date = ""
            for line in old_content.splitlines():
                if line.startswith("date:"):
                    old_date = line.split(":", 1)[1].strip().strip('"')
                    break
            if not old_date:
                old_date = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

            weekly_dir = get_weekly_archive_dir(ARCHIVE_DIR, old_date)
            archive_file = os.path.join(weekly_dir, f"{old_date} 今日待办.md")
            with open(archive_file, "w", encoding="utf-8") as f:
                f.write(old_content)
            print(f"✅ 昨日待办已按自然周自动归档至: {archive_file}")

            # 统计昨日待办打卡完成率并自动写入周报执行矩阵
            try:
                total_items = len(re.findall(r"- \[[ xX]\]", old_content))
                done_items = len(re.findall(r"- \[[xX]\]", old_content))
                if total_items > 0:
                    review_sync_service.update_weekly_todo_matrix(old_date, total_items, done_items)
            except Exception as me:
                print(f"⚠️ 更新周报矩阵异常: {me}")
        except Exception as e:
            print(f"归档旧待办异常: {e}")

    # 2. Load confirmed staged plan
    plan = load_staged_plan()
    if plan.get("date") == today_str and plan.get("todos"):
        todos = plan.get("todos", [])
        schedule_slots = plan.get("schedule_slots", get_default_schedule_slots(today_date))
    else:
        plan = generate_agent_plan(today_str)
        todos = plan.get("todos", [])
        schedule_slots = plan.get("schedule_slots", [])

    # 3. Assemble full Obsidian markdown content
    md_lines = [
        "---",
        "title: 今日核心待办与落地规划 (Daily Action Plan)",
        f"date: {today_str}",
        "priority: 高",
        "tags:",
        "  - todo",
        "  - daily-focus",
        "  - agent-generated",
        "---",
        "",
        f"# 📌 {today_str} ({weekday_str}) 今日核心待办与落地规划",
        "",
        "> 🎯 **今日主线**：由本地 Agent 根据已授权资料生成；资料不足时不主动猜测。",
        "",
        "---",
        "",
        "## 🌟 今日待办清单 (已全量同步飞书官方「任务」列表)",
        ""
    ]

    for item in todos:
        md_lines.append(f"- [ ] **{item}**")

    md_lines.extend([
        "",
        "---",
        "",
        "## ⏱️ 每日敏捷作息与时间盒 (已写入飞书日历)",
        "",
        "| 时段 | 规划核心 | 关键交付 / 目标 |",
        "| :--- | :--- | :--- |"
    ])

    for slot in schedule_slots:
        md_lines.append(f"| **{slot['start']} - {slot['end']}** | {slot['name']} | {slot['summary']} |")

    md_lines.append("")

    with open(config.TODAY_TODO_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"✅ 今日待办已生成并落盘至: {config.TODAY_TODO_PATH}")

    # 3.1 周期复盘全量级联伴生 (日记 / 周报 / 月度回顾)
    try:
        review_sync_service.cascade_sync_all(today_str, todos)
        print("✅ 04 周期复盘（日记/周报/月度回顾）全量级联伴生与同步完成！")
    except Exception as rse:
        print(f"⚠️ 周期复盘级联伴生异常: {rse}")

    # 4. Sync tasks to Feishu Official Task v2 System
    try:
        for t_title in todos:
            create_feishu_task(t_title, description=f"{today_str} 每日待办任务（已同步 Obsidian）")
    except Exception as te:
        print(f"同步飞书官方任务列表异常: {te}")

    # 5. Write schedule events into Feishu Calendar (Strict Clean-Then-Write Idempotency)
    try:
        cal_count = sync_plan_to_calendar({"date": today_str, "schedule_slots": schedule_slots})
        print(f"✅ 已成功将 {cal_count} 项日程原子写入飞书日历（先清后写防重复）！")
    except Exception as ce:
        print(f"写入飞书日历日程异常: {ce}")

    # 6. Push Interactive Card to Feishu
    card_elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"☀️ **{today_str} ({weekday_str}) 今日行动计划已就绪！**\n\n🎯 *计划来自本地 Agent 分析，并同步至已配置的任务、日历与知识库*"
            }
        },
        {"tag": "hr"}
    ]

    todo_md = "📋 **今日核心待办（可直接在飞书任务打勾）：**\n"
    for item in todos:
        todo_md += f"• [ ] **{item}**\n"
    card_elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": todo_md}
    })

    card_elements.append({"tag": "hr"})
    slot_md = "⏱️ **今日日程时间盒安排：**\n"
    for slot in schedule_slots:
        slot_md += f"• **{slot['name']}**：`{slot['start']} ~ {slot['end']}`\n"
    card_elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": slot_md}
    })

    card_elements.append({"tag": "hr"})
    card_elements.append({
        "tag": "note",
        "elements": [
            {"tag": "plain_text", "content": "📁 已同步写入 Obsidian: 03 - 待办事项/今日待办.md | 随时在飞书发“加待办: xxx”追加"}
        ]
    })

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📋 今日核心作战规划 ({today_str})"},
            "template": "blue"
        },
        "elements": card_elements
    }

    return push_feishu_card(card, f"📋 今日核心作战规划已就绪 ({today_str})")

# --- 7. Create Official Feishu Task (Task v2 API) ---
def delete_feishu_task(task_id: str) -> bool:
    """Delete a Feishu task by ID."""
    try:
        token_resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET},
            timeout=10
        )
        token = token_resp.json().get("tenant_access_token")
        if not token:
            return False
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://open.feishu.cn/open-apis/task/v1/tasks/{task_id}"
        res = requests.delete(url, headers=headers, timeout=10)
        return res.json().get("code") == 0
    except Exception as e:
        print(f"⚠️ 删除飞书任务异常: {e}")
        return False

def create_feishu_task(summary: str, description: str = "", due_timestamp: Optional[int] = None, check_duplicate: bool = True) -> Optional[dict]:
    """
    Create a task item in Feishu Task v2 system with Idempotent Deduplication.
    Returns task data dict or None on failure.
    """
    summary = summary.strip()
    if not summary:
        return None

    # Idempotency Guard: prevent duplicate creation if active task with same summary exists
    if check_duplicate:
        try:
            existing = list_feishu_tasks(page_size=50)
            for et in existing:
                if et.get("complete_time") == "0" and et.get("summary", "").strip() == summary:
                    return {"task_id": et.get("id"), "summary": summary, "reused": True}
        except Exception as de:
            pass

    try:
        token_resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET},
            timeout=10
        )
        token = token_resp.json().get("tenant_access_token")
        if not token:
            return None

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        task_payload = {
            "summary": summary,
            "description": description or "由 AGY 智能体自动创建并同步",
            "members": [
                {"id": config.FEISHU_USER_OPEN_ID, "type": "user", "role": "assignee"}
            ]
        }
        if due_timestamp:
            task_payload["due"] = {"timestamp": str(due_timestamp)}

        url = "https://open.feishu.cn/open-apis/task/v2/tasks?user_id_type=open_id"
        res = requests.post(url, headers=headers, json=task_payload, timeout=10)
        res_json = res.json()
        if res_json.get("code") == 0:
            task_data = res_json.get("data", {}).get("task", {})
            return task_data
        else:
            print(f"⚠️ 创建飞书任务失败: {res_json.get('msg')}")
    except Exception as e:
        print(f"⚠️ 创建飞书任务网络异常: {e}")
    return None

def complete_feishu_task(task_id: str) -> bool:
    """
    Mark a Feishu official task as completed using Task v1 complete API.
    """
    try:
        token_resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET},
            timeout=10
        )
        token = token_resp.json().get("tenant_access_token")
        if not token:
            return False

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        url = f"https://open.feishu.cn/open-apis/task/v1/tasks/{task_id}/complete"
        res = requests.post(url, headers=headers, timeout=10)
        res_json = res.json()
        if res_json.get("code") == 0:
            print(f"✅ 成功将飞书任务标记为完成: {task_id}")
            return True
        else:
            print(f"⚠️ 标记飞书任务完成失败 ({task_id}): {res_json.get('msg')}")
            return False
    except Exception as e:
        print(f"⚠️ 标记飞书任务完成网络异常: {e}")
        return False

def list_feishu_tasks(page_size: int = 50) -> List[Dict[str, Any]]:
    """Fetch recent Feishu tasks with auto-retry."""
    for attempt in range(3):
        try:
            token_resp = requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET},
                timeout=10
            )
            token = token_resp.json().get("tenant_access_token")
            if not token:
                continue

            headers = {"Authorization": f"Bearer {token}"}
            url = f"https://open.feishu.cn/open-apis/task/v1/tasks?user_id_type=open_id&page_size={page_size}"
            res = requests.get(url, headers=headers, timeout=10)
            res_json = res.json()
            if res_json.get("code") == 0:
                return res_json.get("data", {}).get("items", [])
        except Exception as e:
            if attempt == 2:
                print(f"⚠️ 获取飞书任务列表网络异常: {e}")
    return []

def complete_task_by_keyword(keyword: str) -> Optional[str]:
    """
    Search Feishu tasks by keyword and complete them.
    Also sync checkmark to Obsidian 今日待办.md.
    """
    kw = keyword.strip()
    if not kw:
        return None

    tasks = list_feishu_tasks()
    completed_names = []
    for t in tasks:
        summary = t.get("summary", "")
        t_id = t.get("id", "")
        # Match keyword in summary
        if kw in summary or summary in kw:
            if complete_feishu_task(t_id):
                completed_names.append(summary)

    # Sync to Obsidian 今日待办.md
    if os.path.exists(config.TODAY_TODO_PATH):
        try:
            with open(config.TODAY_TODO_PATH, "r", encoding="utf-8") as f:
                c = f.read()
            for name in completed_names:
                # Replace - [ ] **name** with - [x] **name**
                c = re.sub(rf"- \[ \] \*\*({re.escape(name)}.*?)\*\*", r"- [x] **\1**", c)
            with open(config.TODAY_TODO_PATH, "w", encoding="utf-8") as f:
                f.write(c)
        except Exception as e:
            print(f"同步勾选 Obsidian 今日待办异常: {e}")

    # Sync checkmarks to 04 - 周期复盘/日记 (Daily)
    try:
        review_sync_service.sync_todo_completion_to_journal(completed_names)
    except Exception as je:
        print(f"⚠️ 同步日记待办勾选异常: {je}")

    if completed_names:
        return f"✅ 已成功将飞书任务、Obsidian 待办与日记打勾完成：\n" + "\n".join([f"• [x] **{n}**" for n in completed_names])
    return None

# --- 8. Append Custom Todo Realtime ---
def append_custom_todo(item_text: str) -> str:
    """Append a custom todo item to 今日待办.md immediately."""
    item_text = item_text.strip()
    if not item_text:
        return "⚠️ 待办事项内容不能为空。"

    if not os.path.exists(config.TODAY_TODO_PATH):
        generate_and_publish_morning_todo()

    try:
        with open(config.TODAY_TODO_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        new_item_line = f"- [ ] **[动态追加] {item_text}**"

        target_header = "## 🌟 今日待办清单 (已全量同步飞书官方「任务」列表)"
        if target_header in content:
            content = content.replace(target_header, f"{target_header}\n{new_item_line}")
        else:
            content = f"{new_item_line}\n" + content

        with open(config.TODAY_TODO_PATH, "w", encoding="utf-8") as f:
            f.write(content)

        feishu_task = create_feishu_task(
            summary=item_text,
            description="由飞书消息实时动态追加（已同步写入 Obsidian 今日待办.md）"
        )
        task_url_info = ""
        if feishu_task and feishu_task.get("url"):
            task_url_info = f"\n🔗 [点击在飞书任务中打勾查看]({feishu_task.get('url')})"

        # 同步更新 staged_plan.json，确保全链路状态强一致
        try:
            plan = load_staged_plan()
            if "todos" in plan and isinstance(plan["todos"], list):
                if item_text not in plan["todos"]:
                    plan["todos"].append(item_text)
                    save_staged_plan(plan)
        except Exception as pe:
            print(f"⚠️ 同步 staged_plan.json 异常: {pe}")

        # 同步增量刷新今日日记
        try:
            cur_todos = []
            for line in content.splitlines():
                if line.strip().startswith("- [ ]") or line.strip().startswith("- [x]"):
                    cur_todos.append(line.split("**")[1] if "**" in line else line.strip())
            review_sync_service.ensure_daily_journal(datetime.date.today().strftime("%Y-%m-%d"), cur_todos)
        except Exception as je:
            print(f"⚠️ 动态追加待办同步日记异常: {je}")

        return f"✅ 已成功将待办同步至「Obsidian 今日待办/日记」与「飞书官方任务」：\n- [ ] **{item_text}**{task_url_info}"
    except Exception as e:
        return f"❌ 追加待办失败: {str(e)}"

# --- 9. Helper: Push Card to Feishu (爪爪openclaw 官方双向通道) ---
def push_feishu_card(card: dict, fallback_title: str) -> bool:
    return feishu_client.send_card(card)

# --- 10. Unified Intent Router for Feishu Bot ---
def handle_todo_intent(user_text: str) -> Optional[str]:
    """
    Fast-track intent recognition for:
    1. Direct todo commands ("加待办: xxx")
    2. Schedule timebox adjustments using the slot name and a requested time
    3. Plan confirmations ("确认", "没问题", "可以", "按这个来")
    """
    text = user_text.strip()

    # 1. Direct addition:
    # 1.1 Natural language patterns (e.g. 给我加一个任务xxx / 加任务: xxx / 帮我加个待办xxx)
    add_match = re.match(r"^(?:给我|帮我|麻烦)?(?:加|添加|增加|加一个|加个|加上)(?:一个)?(?:任务|待办|日程|事项)[:：\s]*(.+)$", text)
    if add_match:
        item = add_match.group(1).strip()
        if item:
            return append_custom_todo(item)

    # 1.2 Traditional prefixes
    for prefix in ["加待办:", "加待办：", "添加待办:", "添加待办：", "加待办", "添加待办", "加任务:", "加任务：", "添加任务:", "添加任务：", "加任务", "添加任务"]:
        if text.startswith(prefix):
            item = text[len(prefix):].strip(" :：")
            if item:
                return append_custom_todo(item)
    if text.startswith("待办:") or text.startswith("待办：") or text.startswith("任务:") or text.startswith("任务："):
        item = text[3:].strip()
        if item:
            return append_custom_todo(item)

    # Load current staged plan
    plan = load_staged_plan()

    # 2. Generic schedule adjustment. The slot must be named in the request;
    # there is deliberately no domain-specific schedule vocabulary here.
    adjustment_words = ["改到", "调到", "改至", "推迟", "延后", "调整为", "改成", "改为"]
    time_match = re.search(r"(\d{1,2})[:：点](\d{0,2})", text)
    if time_match and any(word in text for word in adjustment_words):
        new_hour = int(time_match.group(1))
        new_minute = int(time_match.group(2) or 0)
        if not 0 <= new_hour <= 23 or not 0 <= new_minute <= 59:
            return None
        new_start = f"{new_hour:02d}:{new_minute:02d}"
        slots = plan.get("schedule_slots", [])
        matched = None
        for slot in slots:
            slot_name = str(slot.get("name", "")).strip()
            if slot_name and slot_name in text:
                matched = slot
                break
        if matched:
            try:
                old_start = datetime.datetime.strptime(matched.get("start", "00:00"), "%H:%M")
                old_end = datetime.datetime.strptime(matched.get("end", "01:00"), "%H:%M")
                duration_minutes = max(30, int((old_end - old_start).total_seconds() // 60))
            except (TypeError, ValueError):
                duration_minutes = 60
            end_dt = datetime.datetime.combine(datetime.date.today(), datetime.time(new_hour, new_minute))
            end_dt += datetime.timedelta(minutes=duration_minutes)
            matched["start"] = new_start
            matched["end"] = end_dt.strftime("%H:%M")
            matched["summary"] = f"{matched.get('summary', matched.get('name', '时间块'))} ({new_start}~{matched['end']})"
            save_staged_plan(plan)
            return f"✅ 已将“{matched.get('name', '时间块')}”调整为 `{new_start} ~ {matched['end']}`。"

    # 3. Todo addition in review: 加上：xxx / 还要加上：xxx
    for prefix in ["加上:", "加上：", "还要加上:", "还要加上：", "再加上:", "再加上：", "加上"]:
        if text.startswith(prefix):
            item = text[len(prefix):].strip(" :：")
            if item and len(item) >= 2:
                todos = plan.get("todos", [])
                if item not in todos:
                    todos.append(item)
                    plan["todos"] = todos
                    save_staged_plan(plan)
                return f"✅ 收到！已为您追加确认明日待办：\n• **{item}**\n\n明早 06:00 将准时汇总落盘并同步至飞书任务！"

    # 4. Direct Task Completion: 打卡: xxx / 完成: xxx / xxx已完成 / xxx已做 / 完成了xxx
    for prefix in ["完成待办:", "完成待办：", "完成任务:", "完成任务：", "打卡:", "打卡：", "已完成:", "已完成："]:
        if text.startswith(prefix):
            item = text[len(prefix):].strip(" :：")
            if item:
                res = complete_task_by_keyword(item)
                if res:
                    return res

    # Quick matching for task completion statements (e.g. 收被子已完成 / 单词学习已打卡)
    if any(text.endswith(sfx) for sfx in ["已完成", "已搞定", "已打卡", "搞定了", "完成了"]):
        for sfx in ["已完成", "已搞定", "已打卡", "搞定了", "完成了"]:
            if text.endswith(sfx):
                item = text[:-len(sfx)].strip(" ：:,，")
                if item:
                    res = complete_task_by_keyword(item)
                    if res:
                        return res

def sync_plan_to_calendar(plan_data: Dict[str, Any]) -> int:
    """
    Strict Dual-Write Rule: Immediately write all schedule slots to Feishu Calendar OpenAPI.
    Ensures calendar is updated at review time AND morning time!
    """
    target_date_str = plan_data.get("date", "")
    if not target_date_str:
        return 0

    try:
        t_year, t_month, t_day = map(int, target_date_str.split("-"))
        target_date = datetime.date(t_year, t_month, t_day)
    except Exception:
        return 0

    slots = plan_data.get("schedule_slots", [])
    if not slots:
        return 0

    # 1. Clean existing events on target date to avoid duplicates
    try:
        feishu_calendar.calendar_mgr.clean_day_events(target_date)
    except Exception as e:
        print(f"清理旧日程异常: {e}")

    # 2. Immediately write slots to Feishu Calendar
    written_count = 0
    for s in slots:
        try:
            s_hour, s_min = map(int, s["start"].split(":"))
            e_hour, e_min = map(int, s["end"].split(":"))
            s_dt = datetime.datetime.combine(target_date, datetime.time(s_hour, s_min))
            e_dt = datetime.datetime.combine(target_date, datetime.time(e_hour, e_min))
            ok, ev_id = feishu_calendar.calendar_mgr.create_silent_event(
                summary=s["summary"],
                start_dt=s_dt,
                end_dt=e_dt,
                description=s.get("desc", s["summary"]),
                reminder_minutes=15
            )
            if ok:
                written_count += 1
        except Exception as se:
            print(f"写入日历槽位异常 ({s.get('name')}): {se}")

    return written_count

def sync_plan_to_feishu_tasks(plan_data: Dict[str, Any]) -> int:
    """
    Strict Dual-Write Rule: Immediately batch create/sync all staged todos to Feishu Task OpenAPI.
    Ensures tasks are created at review time AND morning time!
    """
    todos = plan_data.get("todos", [])
    if not todos:
        return 0

    target_date_str = plan_data.get("date", datetime.datetime.now().strftime("%Y-%m-%d"))
    created_count = 0
    for t_title in todos:
        try:
            task = create_feishu_task(
                summary=t_title,
                description=f"{target_date_str} 核心作战待办（已同步 Obsidian 知识库）"
            )
            if task:
                created_count += 1
        except Exception as e:
            print(f"创建飞书任务异常 ({t_title}): {e}")

    return created_count

    # 5. Evening Review Confirmation: 明确针对预审/排期的指令
    # 严格限定专用词汇，避免截胡通用审批词（如“确认”、“好的”、“执行”）
    explicit_review_confirm_keywords = [
        "确认预排", "确认明日预审", "确认日程", "确认排期", "确认明日待办", 
        "锁定排期", "锁定日程", "锁定明日", "排期没问题", "日程可以", "按主线排期"
    ]
    if any(k in text for k in explicit_review_confirm_keywords):
        now_hour = datetime.datetime.now().hour
        if now_hour >= 21 or now_hour <= 2:
            plan["confirmed"] = True
            save_staged_plan(plan)
            # 严格贯彻双写铁律：晚间确认时必须当场立即双写飞书日历与飞书任务！
            cal_count = sync_plan_to_calendar(plan)
            task_count = sync_plan_to_feishu_tasks(plan)
            return (
                f"✅ 收到！已严格执行【双节点×双载体双写铁律】：\n"
                f"1. 📅 **飞书官方日历**：已当场立即写入全部 {cal_count} 项敏捷时间盒日程（含15分钟提前强提醒闹钟）！\n"
                f"2. 📋 **飞书官方任务**：已当场立即批量创建全部 {task_count} 项核心待办（可直接打勾）！\n"
                f"3. 📁 **知识库底册**：排期已正式锁定，明早 06:00 晨启时将执行二次对账生成 Obsidian 今日待办.md。"
            )

    return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Daily Todo & Schedule Service")
    parser.add_argument("--evening", action="store_true", help="Run evening review")
    parser.add_argument("--morning", action="store_true", help="Run 06:00 Morning Generation")
    parser.add_argument("--add", type=str, help="Add custom todo item")
    parser.add_argument("--complete", type=str, help="Complete todo item by keyword")
    args = parser.parse_args()

    if args.evening:
        send_evening_review_prompt()
    elif args.morning:
        generate_and_publish_morning_todo()
    elif args.add:
        print(append_custom_todo(args.add))
    elif args.complete:
        res = complete_task_by_keyword(args.complete)
        print(res or f"未找到匹配 '{args.complete}' 的任务")
    else:
        print("请指定参数: --evening / --morning / --add 'xxx' / --complete 'xxx'")
