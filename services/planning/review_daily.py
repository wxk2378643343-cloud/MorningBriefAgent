"""Daily journal synchronization."""

from __future__ import annotations

import os
import re
from typing import List

from . import review_common as common


def ensure_daily_journal(date_str: str, todos: List[str]) -> str:
    common.ensure_review_directories()
    date = common.parse_date(date_str)
    week_code, week_folder, _, _ = common.get_week_info(date)
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekly_filename = f"{week_folder} 周报.md"
    todo_block = "\n".join(f"- [ ] **{item}**" for item in todos)
    file_path = os.path.join(common.DAILY_DIR, f"{date_str}.md")

    if not os.path.exists(file_path):
        content = f"""---
date: {date_str}
day: {weekdays[date.weekday()]}
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
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(content)
        print(f"✅ 已自动伴生创建今日复盘日记: {file_path}")
        return file_path

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            existing = file.read()
        header = "## 📋 二、今日核心待办执行闭环"
        if header in existing:
            for item in todos:
                if re.search(rf"- \[x\] \*\*({re.escape(item)}.*?)\*\*", existing):
                    todo_block = re.sub(
                        rf"- \[ \] \*\*({re.escape(item)}.*?)\*\*",
                        r"- [x] **\1**",
                        todo_block,
                    )
            updated = common.replace_markdown_section(existing, header, todo_block)
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(updated)
        print(f"✅ 已增量同步待办至今日日记: {file_path}")
    except OSError as exc:
        print(f"⚠️ 更新现有日记待办块异常: {exc}")
    return file_path


def sync_todo_completion_to_journal(
    completed_names: List[str],
    date_str: str | None = None,
) -> bool:
    if not completed_names:
        return False
    date = common.parse_date(date_str)
    file_path = os.path.join(common.DAILY_DIR, f"{date:%Y-%m-%d}.md")
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        changed = False
        for name in completed_names:
            pattern = rf"- \[ \] \*\*({re.escape(name)}.*?)\*\*"
            if re.search(pattern, content):
                content = re.sub(pattern, r"- [x] **\1**", content)
                changed = True
        if changed:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(content)
            print(f"✅ 已同步将打卡状态打勾至日记: {file_path}")
        return changed
    except OSError as exc:
        print(f"⚠️ 同步日记勾选状态异常: {exc}")
        return False
