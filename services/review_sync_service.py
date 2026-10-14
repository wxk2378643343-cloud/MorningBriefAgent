#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Review Sync Service (周期复盘全自动级联同步引擎)
实现日记、周报、月度回顾与待办事项的全自动双向联动：
1. 日记自动伴生与待办镜像注入
2. 打卡指令实时双写打勾 ([ ] -> [x])
3. 周报自然周框架自愈保全与待办矩阵跟踪
4. 月度回顾全月周报索引汇流与里程碑看板
"""

import os
import sys
import re
import datetime
from typing import List, Dict, Any, Optional, Tuple

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

VAULT_ROOT = config.VAULT_ROOT
DAILY_DIR = config.REVIEW_DAILY_DIR
WEEKLY_DIR = config.REVIEW_WEEKLY_DIR
MONTHLY_DIR = config.REVIEW_MONTHLY_DIR
TODO_ARCHIVE_DIR = config.TODO_ARCHIVE_DIR

def ensure_review_directories() -> None:
    for directory in (DAILY_DIR, WEEKLY_DIR, MONTHLY_DIR, TODO_ARCHIVE_DIR):
        if directory:
            os.makedirs(directory, exist_ok=True)


def replace_markdown_section(content: str, header: str, new_body: str) -> str:
    """Replace one Markdown section body while preserving all later sections."""
    pattern = re.compile(
        rf"(^\s*{re.escape(header)}\s*$\n)(.*?)(?=^\s*---\s*$|^\s*##\s+|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    updated, count = pattern.subn(
        lambda match: f"{match.group(1)}{new_body.rstrip()}\n\n",
        content,
        count=1,
    )
    return updated if count else content


def parse_date(date_str: Optional[str] = None) -> datetime.date:
    if not date_str:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return datetime.date.today()


def get_week_info(dt: datetime.date) -> Tuple[str, str, str, str]:
    """返回 (week_code, folder_name, monday_str, sunday_str)"""
    year, week, weekday = dt.isocalendar()
    monday = dt - datetime.timedelta(days=weekday - 1)
    sunday = monday + datetime.timedelta(days=6)
    week_code = f"{year}-W{week:02d}"
    folder_name = f"{week_code} ({monday.strftime('%m.%d')} - {sunday.strftime('%m.%d')})"
    return week_code, folder_name, monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


# ==============================================================================
# 1. 日度日记 (Daily Journal) 伴生与待办双写
# ==============================================================================

def ensure_daily_journal(date_str: str, todos: List[str]) -> str:
    """
    确保指定日期的日记文件存在；若不存在则自动生成模板并镜像待办，若已存在则更新待办清单块。
    """
    ensure_review_directories()
    dt = parse_date(date_str)
    week_code, week_folder, mon_str, sun_str = get_week_info(dt)
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    day_name = weekday_names[dt.weekday()]
    
    file_path = os.path.join(DAILY_DIR, f"{date_str}.md")
    weekly_filename = f"{week_folder} 周报.md"

    # 构造待办清单 Markdown 文本
    todo_lines = []
    for item in todos:
        todo_lines.append(f"- [ ] **{item}**")
    todo_block = "\n".join(todo_lines)

    if not os.path.exists(file_path):
        content = f"""---
date: {date_str}
day: {day_name}
week: {week_code}
tags:
  - daily
  - review
  - morning-brief
  - agent-generated
  - daily-review
  - todo-linkage
---

# 📅 {date_str} 每日工作与敏捷复盘 (Daily Report)

> 💡 **今日一句话总结**：**由本地 Agent 根据当日资料生成。**
> 
> 🔗 **待办与周报双链直达**：
> • 📋 **今日待办清单**：由配置的计划输出路径提供
> • 🚀 **本周报告**：{weekly_filename}

---

## 🎯 一、今日核心战役与交付复盘 (Top Achievements)

- 

---

## 📋 二、今日核心待办执行闭环

{todo_block}
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 已自动伴生创建今日复盘日记: {file_path}")
    else:
        # 已存在时，检查是否需要同步更新待办块
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing = f.read()

            target_header = "## 📋 二、今日核心待办执行闭环"
            if target_header in existing:
                # 保留原有打勾状态
                for item in todos:
                    checked_pattern = rf"- \[x\] \*\*({re.escape(item)}.*?)\*\*"
                    if re.search(checked_pattern, existing):
                        todo_block = re.sub(rf"- \[ \] \*\*({re.escape(item)}.*?)\*\*", r"- [x] **\1**", todo_block)
                updated = replace_markdown_section(existing, target_header, todo_block)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(updated)
            print(f"✅ 已增量同步待办至今日日记: {file_path}")
        except Exception as e:
            print(f"⚠️ 更新现有日记待办块异常: {e}")

    return file_path


def sync_todo_completion_to_journal(completed_names: List[str], date_str: Optional[str] = None) -> bool:
    """
    打卡时同步将日记中的对应待办事项打勾: - [ ] **item** -> - [x] **item**
    """
    if not completed_names:
        return False
    
    dt = parse_date(date_str)
    date_formatted = dt.strftime("%Y-%m-%d")
    file_path = os.path.join(DAILY_DIR, f"{date_formatted}.md")
    if not os.path.exists(file_path):
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        changed = False
        for name in completed_names:
            pattern = rf"- \[ \] \*\*({re.escape(name)}.*?)\*\*"
            if re.search(pattern, content):
                content = re.sub(pattern, r"- [x] **\1**", content)
                changed = True

        if changed:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ 已同步将打卡状态打勾至日记: {file_path}")
            return True
    except Exception as e:
        print(f"⚠️ 同步日记勾选状态异常: {e}")
    return False


# ==============================================================================
# 2. 周度周报 (Weekly Report) 自愈保全与矩阵跟踪
# ==============================================================================

def ensure_weekly_report(date_str: str) -> str:
    """
    确保当周的周报存在，若不存在则创建标准周报骨架，并挂载待办流水穿透与月报双链。
    """
    ensure_review_directories()
    dt = parse_date(date_str)
    week_code, week_folder, mon_str, sun_str = get_week_info(dt)
    month_str = dt.strftime("%Y-%m")
    
    # 查找可能已存在的同周周报文件
    matched_file = None
    for f in os.listdir(WEEKLY_DIR):
        if f.startswith(week_code) and f.endswith(".md"):
            matched_file = os.path.join(WEEKLY_DIR, f)
            break

    if matched_file:
        return matched_file

    file_name = f"{week_folder} 周报.md"
    file_path = os.path.join(WEEKLY_DIR, file_name)

    monthly_filename = f"{month_str} 月度敏捷与学力复盘.md"

    content = f"""---
title: "{week_folder} 敏捷工程与学力周报"
week: "{week_code}"
date_range: "{mon_str} ~ {sun_str}"
created: {date_str}
updated: {date_str}
tags:
  - weekly
  - review
  - sprint
  - morning-brief
  - milestone
---

# 🚀 {week_folder} 敏捷工程与学力周报

> 💡 **本周总评（Sprint Retrospective）**：  
> **{week_code} 周期总结由本地 Agent 根据已归档资料生成。**
> 
> 🔗 **层级双链直达**：
> • 📋 **本周待办流水**：{week_folder}
> • 🌕 **所属月度回顾**：{monthly_filename}

---

## 🎯 一、核心战役交付全景

- 

---

## 📊 二、本周待办每日执行矩阵

| 日期 | 星期 | 待办总数 | 已完成 | 完成率 | 达成状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |

---

## 🔗 三、本周关键资产索引
- **本周待办文件夹**：`{week_folder}/`
- **今日核心待办**：由配置的计划输出路径提供
- **今日复盘日记**：`{date_str}.md`
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 已自动生成本周周报框架: {file_path}")
    return file_path


def update_weekly_todo_matrix(date_str: str, total_count: int, completed_count: int) -> bool:
    """
    向周报的「本周待办每日执行矩阵」表格中追加或更新指定日期的执行统计
    """
    dt = parse_date(date_str)
    week_code, week_folder, _, _ = get_week_info(dt)
    weekly_file = ensure_weekly_report(date_str)

    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    day_name = weekday_names[dt.weekday()]
    rate_str = f"{(completed_count / total_count * 100):.0f}%" if total_count > 0 else "0%"
    status_icon = "🟢 优秀" if completed_count >= total_count else ("🟡 良好" if completed_count >= total_count * 0.7 else "🔴 待补齐")

    row_line = f"| {date_str} | {day_name} | {total_count} | {completed_count} | {rate_str} | {status_icon} |"

    try:
        with open(weekly_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查是否已包含这一天
        if f"| {date_str} |" in content:
            # 替换已有行
            content = re.sub(
                rf"^\|\s*{re.escape(date_str)}\s*\|[^\r\n]*$",
                row_line,
                content,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            # 追加到矩阵表格下方
            target_table_header = "| :--- | :--- | :--- | :--- | :--- | :--- |"
            if target_table_header in content:
                content = content.replace(target_table_header, f"{target_table_header}\n{row_line}")
            else:
                content += f"\n{row_line}\n"

        with open(weekly_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 已将 {date_str} 待办统计更新进周报矩阵: {completed_count}/{total_count} ({rate_str})")
        return True
    except Exception as e:
        print(f"⚠️ 更新周报待办矩阵异常: {e}")
        return False


# ==============================================================================
# 3. 月度回顾 (Monthly Review) 自愈保全与周报索引汇流
# ==============================================================================

def ensure_monthly_report(date_str: str) -> str:
    """
    确保当月的月度回顾文档存在；若不存在则自动扫描全月所有自然周并挂载索引。
    """
    ensure_review_directories()
    dt = parse_date(date_str)
    month_str = dt.strftime("%Y-%m")
    year = dt.year
    month = dt.month

    file_name = f"{month_str} 月度敏捷与学力复盘.md"
    file_path = os.path.join(MONTHLY_DIR, file_name)

    # 计算当月包含的所有自然周
    first_day = datetime.date(year, month, 1)
    if month == 12:
        last_day = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)

    weeks_set = set()
    cur = first_day
    while cur <= last_day:
        w_code, w_folder, _, _ = get_week_info(cur)
        weeks_set.add((w_code, w_folder))
        cur += datetime.timedelta(days=1)

    sorted_weeks = sorted(list(weeks_set), key=lambda x: x[0])
    
    # 构造周报索引列表
    weekly_index_lines = []
    for w_code, w_folder in sorted_weeks:
        # 匹配实际存在的周报文件名
        matched = f"{w_folder} 周报.md"
        for wf in os.listdir(WEEKLY_DIR):
            if wf.startswith(w_code) and wf.endswith(".md"):
                matched = wf
                break
        weekly_index_lines.append(f"- 🚀 **{w_code}**：{matched} · 待办流水：{w_folder}/")

    weekly_index_block = "\n".join(weekly_index_lines)

    if not os.path.exists(file_path):
        content = f"""---
title: "{month_str} 月度敏捷与学力全景复盘"
month: "{month_str}"
created: {date_str}
updated: {date_str}
tags:
  - monthly
  - review
  - sprint
  - agent-generated
  - monthly-review
  - milestone
---

# 🌕 {month_str} 月度敏捷与学力全景复盘

> 💡 **月度总评（Monthly Retrospective）**：  
> **{month_str} 月度重点与结论由本地 Agent 根据已归档资料生成。**

---

## 📅 一、全月敏捷周报穿透索引

{weekly_index_block}

---

## 🎯 二、月度核心里程碑交付

```mermaid
mindmap
  root(({month_str}<br/>核心战役))
    1. 用户目标与重要进展
      由 Agent 从归档资料中提取
    2. 智能体工程落地
      MorningBriefAgent 分层架构投产
      微信多模态全时序时空归档
      市场信息摘要与风险记录
      待办事项与周期复盘全量联动
    3. 下一周期建议
      由 Agent 基于证据提出
```

---

## 📊 三、全月执行健康度总览

| 维度 | 月度目标 | 实际达成 | 健康度 |
| :--- | :--- | :--- | :--- |
| **目标完成情况** | 由 Agent 统计 | 持续统计中 | 🟡 待分析 |
| **重要进展** | 由 Agent 提取 | 持续统计中 | 🟡 待分析 |
| **待办完成率** | 自动统计 | 持续统计中 | 🟡 待分析 |
| **风险与阻塞** | 由 Agent 提取 | 持续统计中 | 🟡 待分析 |

---

## 🔗 四、月度关键资产直达
- **月度周报集合**：由 `REVIEW_WEEKLY_DIR` 配置
- **每日日记集合**：由 `REVIEW_DAILY_DIR` 配置
- **待办历史归档**：由 `TODO_ARCHIVE_DIR` 配置
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 已自动生成月度复盘文档: {file_path}")
    else:
        # 已存在时，增量更新周报索引
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                c = f.read()
            header = "## 📅 一、全月敏捷周报穿透索引"
            if header in c:
                updated = replace_markdown_section(c, header, weekly_index_block)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(updated)
            print(f"✅ 已刷新月度复盘周报索引: {file_path}")
        except Exception as e:
            print(f"⚠️ 更新月报周报索引异常: {e}")

    return file_path


# ==============================================================================
# 4. 全量联动中枢入口
# ==============================================================================

def cascade_sync_all(date_str: str, todos: List[str]) -> Dict[str, str]:
    """
    一键执行日、周、月全量级联保全与同步
    """
    daily_file = ensure_daily_journal(date_str, todos)
    weekly_file = ensure_weekly_report(date_str)
    monthly_file = ensure_monthly_report(date_str)
    
    return {
        "daily": daily_file,
        "weekly": weekly_file,
        "monthly": monthly_file
    }
