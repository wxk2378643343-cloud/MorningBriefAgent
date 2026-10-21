#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Todo & Schedule Service (Unified Planning & Evening Review Agent)
1. Evening review: Scans configured chat logs, prepares Agent-generated Todos + Calendar Schedule Slots, sends a unified review card to Feishu.
2. Evening Interaction: User can adjust configured schedule slots, add todos, or confirm the plan.
3. Morning routine: Archives yesterday's plan when an output path is configured, creates Feishu official tasks (Task v2),
   and writes schedule events directly to Feishu Calendar (with 15-min advance alarms).
4. 24/7 Realtime: Supports adding custom todos anytime via Feishu message ("加待办: xxx").
"""

import os
import sys
import io
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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.runtime import config
from core.integrations.feishu import calendar as feishu_calendar
from core.integrations.feishu import idempotency
from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.client import feishu_client
from core.integrations.sync_outbox import sync_outbox
from . import feishu_tasks
from . import plan_generation
from . import todo_analysis, todo_archive, todo_candidates, todo_renderer


def delete_feishu_task(task_id: str) -> bool:
    return feishu_tasks.delete_feishu_task(task_id, gateway=feishu_gateway)


def list_feishu_tasks(page_size: int = 50) -> List[Dict[str, Any]]:
    return feishu_tasks.list_feishu_tasks(page_size, gateway=feishu_gateway)


def create_feishu_task(
    summary: str,
    description: str = "",
    due_timestamp: Optional[int] = None,
    check_duplicate: bool = True,
    idempotency_key: str = "",
) -> Optional[dict]:
    return feishu_tasks.create_feishu_task(
        summary,
        description,
        due_timestamp,
        check_duplicate,
        idempotency_key,
        gateway=feishu_gateway,
    )


def complete_feishu_task(task_id: str) -> bool:
    return feishu_tasks.complete_feishu_task(task_id, gateway=feishu_gateway)


def complete_task_by_keyword(keyword: str) -> Optional[str]:
    return feishu_tasks.complete_task_by_keyword(keyword, gateway=feishu_gateway)

SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
from . import review_sync as review_sync_service
from . import calendar_sync, task_sync
from storage.planning import attach_feishu_event_id, attach_feishu_task_id

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
STAGED_PLAN_FILE = str(plan_generation.DEFAULT_STAGED_PLAN_FILE)

ARCHIVE_DIR = config.TODO_ARCHIVE_DIR

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

get_default_baseline_todos = plan_generation.get_default_baseline_todos
get_default_schedule_slots = plan_generation.get_default_schedule_slots
generate_agent_plan = plan_generation.generate_agent_plan


def load_staged_plan() -> Dict[str, Any]:
    return plan_generation.load_staged_plan(STAGED_PLAN_FILE)


def save_staged_plan(
    data: Dict[str, Any],
    *,
    metadata_database_path: Optional[str] = None,
    database_path: Optional[str] = None,
) -> None:
    plan_generation.save_staged_plan(
        data,
        STAGED_PLAN_FILE,
        metadata_database_path=metadata_database_path or config.METADATA_DATABASE_PATH,
        database_path=database_path,
    )

def extract_candidates_from_chat() -> List[str]:
    return todo_candidates.extract_candidates(
        sync_database=sync_wechat_database,
        message_db=WECHAT_MSG_DB,
        feishu_log=FEISHU_BOT_LOG,
        todo_path=config.TODAY_TODO_PATH,
        keywords=(
            "记得", "需要", "明天要", "待办", "处理一下", "安排", "改一下",
            "改下", "查一下", "确认下", "发一下", "买", "修复", "更新",
            "跟进", "测试",
        ),
        log_keywords=("改", "换成", "加", "明天", "备忘", "待办", "计划", "做"),
    )

# --- 5. Send Unified Evening Review Prompt ---
def send_evening_review_prompt() -> bool:
    """Send a review card for Agent-generated todos and schedule slots."""
    now = datetime.datetime.now()
    tomorrow_date = (now + datetime.timedelta(days=1)).date()
    tomorrow_str = tomorrow_date.strftime("%Y-%m-%d")
    weekday_str = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][tomorrow_date.weekday()]

    candidates = extract_candidates_from_chat()
    analysis = todo_analysis.analyze_candidates(candidates, tomorrow_str)
    generated_plan = generate_agent_plan(tomorrow_str, analysis)
    all_todos = list(generated_plan.get("todos", []))
    default_slots = list(generated_plan.get("schedule_slots", []))
    if not all_todos:
        all_todos = [
            str(item.get("title", "")).strip()
            for item in analysis.get("valid_items", [])
            if str(item.get("title", "")).strip()
        ]

    # Save to staged plan
    plan_data = {
        "date": tomorrow_str,
        "weekday": weekday_str,
        "todos": all_todos,
        "schedule_slots": default_slots,
        "candidates": candidates,
        "analysis": analysis,
        "confirmed": False
    }
    save_staged_plan(plan_data)

    card = todo_renderer.build_evening_review_card(plan_data)
    return push_feishu_card(card, f"🌙 明日待办与日程综合预审 ({tomorrow_str})")

def get_weekly_archive_dir(archive_base: str, date_str: str) -> str:
    return todo_archive.get_weekly_archive_dir(archive_base, date_str)


# --- 6. Generate and Publish Morning Todo ---
def generate_and_publish_morning_todo() -> bool:
    """Generate today's configured plan output and sync tasks/calendar."""
    now = datetime.datetime.now()
    today_date = now.date()
    today_str = today_date.strftime("%Y-%m-%d")
    weekday_str = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][today_date.weekday()]

    # 1. Archive yesterday's plan into the configured archive folder
    if config.TODAY_TODO_PATH and os.path.exists(config.TODAY_TODO_PATH):

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

            weekly_dir = get_weekly_archive_dir(ARCHIVE_DIR, old_date) if ARCHIVE_DIR else ""
            if not weekly_dir:
                print("ℹ️ 未配置 TODO_ARCHIVE_DIR，跳过旧计划归档。")
            else:
                archive_file = os.path.join(weekly_dir, f"{old_date} plan.md")
                with open(archive_file, "w", encoding="utf-8") as f:
                    f.write(old_content)
                print(f"✅ 昨日计划已按自然周归档至: {archive_file}")

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

    if config.TODAY_TODO_PATH:
        os.makedirs(os.path.dirname(config.TODAY_TODO_PATH), exist_ok=True)
        with open(config.TODAY_TODO_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        print(f"✅ 计划已生成并落盘至: {config.TODAY_TODO_PATH}")
    else:
        print("ℹ️ 未配置 TODAY_TODO_PATH，跳过本地 Markdown 写入。")

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
            {"tag": "plain_text", "content": "📁 已同步写入已配置的本地计划文件 | 随时在飞书发“加待办: xxx”追加"}
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

# --- 8. Append Custom Todo Realtime ---
def append_custom_todo(item_text: str) -> str:
    """Append a custom todo item to the configured local plan immediately."""
    item_text = item_text.strip()
    if not item_text:
        return "⚠️ 待办事项内容不能为空。"

    if not config.TODAY_TODO_PATH:
        return "⚠️ 未配置 TODAY_TODO_PATH，无法追加到本地计划文件。"
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
            description="由飞书消息实时动态追加（已同步写入本地计划文件）",
            idempotency_key=idempotency.make_key(
                "feishu-task", datetime.date.today().isoformat(), item_text
            ),
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

        return f"✅ 已成功将待办同步至本地计划文件与飞书任务：\n- [ ] **{item_text}**{task_url_info}"
    except Exception as e:
        return f"❌ 追加待办失败: {str(e)}"

# --- 9. Helper: Push Card to Feishu (爪爪openclaw 官方双向通道) ---
def push_feishu_card(card: dict, fallback_title: str) -> bool:
    return feishu_gateway.send_card_once(
        card,
        idempotency.make_key("feishu-card", fallback_title, datetime.date.today().isoformat()),
    )

# --- 10. Unified Intent Router for Feishu Bot ---
def handle_todo_intent(user_text: str) -> Optional[str]:
    """
    Fast-track intent recognition for:
    1. Direct todo commands ("加待办: xxx")
    2. Schedule timebox adjustments using the slot name and a requested time
    3. Plan confirmations ("确认", "没问题", "可以", "按这个来")
    """
    text = user_text.strip()

    # Simple, low-risk natural language scheduling: use a transparent default
    # time instead of blocking the user on a confirmation round-trip.
    morning_match = re.match(
        r"^(?:明天|明日)上午(?:提醒我|安排我|帮我)?(.+)$", text
    )
    if morning_match:
        title = morning_match.group(1).strip(" ：:，,。")
        if title:
            target_date = datetime.date.today() + datetime.timedelta(days=1)
            plan = {
                "date": target_date.isoformat(),
                "todos": [title],
                "schedule_slots": [{
                    "name": title,
                    "start": "09:00",
                    "end": "10:00",
                    "summary": title,
                    "desc": "由飞书消息自动安排；默认使用上午 09:00–10:00。",
                }],
            }
            save_staged_plan(plan)
            task_count = sync_plan_to_feishu_tasks(plan)
            calendar_count = sync_plan_to_calendar(plan)
            return (
                f"✅ 已安排明天 09:00–10:00：**{title}**。\n"
                f"飞书任务同步 {task_count} 项，日程同步 {calendar_count} 项。"
                "如果需要调整，直接告诉我新的时间即可。"
            )

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
                return f"✅ 收到！已为您追加确认明日待办：\n• **{item}**\n\n后续运行计划时将同步至飞书任务！"

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

    # 5. Evening Review Confirmation: 明确针对预审/排期的指令
    # 严格限定专用词汇，避免截胡通用审批词（如“确认”、“好的”、“执行”）
    explicit_review_confirm_keywords = [
        "确认预排", "确认明日预审", "确认日程", "确认排期", "确认明日待办",
        "锁定排期", "锁定日程", "锁定明日", "排期没问题", "日程可以", "按主线排期"
    ]
    if any(keyword in text for keyword in explicit_review_confirm_keywords):
        now_hour = datetime.datetime.now().hour
        if now_hour >= 21 or now_hour <= 2:
            plan["confirmed"] = True
            save_staged_plan(plan)
            cal_count = sync_plan_to_calendar(plan)
            task_count = sync_plan_to_feishu_tasks(plan)
            return (
                f"✅ 收到！已严格执行【双节点×双载体双写铁律】：\n"
                f"1. 📅 **飞书官方日历**：已当场立即写入全部 {cal_count} 项敏捷时间盒日程（含15分钟提前强提醒闹钟）！\n"
                f"2. 📋 **飞书官方任务**：已当场立即批量创建全部 {task_count} 项核心待办（可直接打勾）！\n"
                f"3. 📁 **本地计划文件**：排期已正式锁定，下一次运行计划时将执行二次对账并写入配置路径。"
            )

    return None

def sync_plan_to_calendar(plan_data: Dict[str, Any]) -> int:
    try:
        source_id = f"plan:{plan_data.get('date', 'unknown')}"
        target_date = str(plan_data.get("date", ""))
        return calendar_sync.sync_plan_to_calendar(
            plan_data,
            feishu_gateway,
            record_event=lambda slot, event_id: attach_feishu_event_id(
                title=slot.name,
                source_id=source_id,
                start_at=f"{target_date}T{slot.start}:00",
                end_at=f"{target_date}T{slot.end}:00",
                feishu_event_id=event_id,
            ),
        )
    except (TypeError, ValueError) as exc:
        print(f"⚠️ 日历同步跳过，计划契约无效: {exc}")
        return 0

def sync_plan_to_feishu_tasks(plan_data: Dict[str, Any]) -> int:
    try:
        source_id = f"plan:{plan_data.get('date', 'unknown')}"
        return task_sync.sync_plan_to_feishu_tasks(
            plan_data,
            create_feishu_task,
            record_task=lambda title, task_id: attach_feishu_task_id(
                title=title,
                source_id=source_id,
                due_date=str(plan_data.get("date", "")) or None,
                feishu_task_id=task_id,
            ),
        )
    except (TypeError, ValueError) as exc:
        print(f"⚠️ 任务同步跳过，计划契约无效: {exc}")
        return 0

def morning_routine() -> bool:
    """Stable public entry point used by the CLI and Windows Task Scheduler."""
    return generate_and_publish_morning_todo()


def evening_routine() -> bool:
    """Stable public entry point used by the CLI and Windows Task Scheduler."""
    return send_evening_review_prompt()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Daily Todo & Schedule Service")
    parser.add_argument("--evening", action="store_true", help="Run evening review")
    parser.add_argument("--morning", action="store_true", help="Run morning plan generation")
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
