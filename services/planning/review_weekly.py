"""Weekly review report and todo matrix synchronization."""

from __future__ import annotations

import os
import re

from . import review_common as common


def ensure_weekly_report(date_str: str) -> str:
    common.ensure_review_directories()
    week_code, folder, monday, sunday = common.get_week_info(common.parse_date(date_str))
    for name in os.listdir(common.WEEKLY_DIR):
        if name.startswith(week_code) and name.endswith(".md"):
            return os.path.join(common.WEEKLY_DIR, name)
    path = os.path.join(common.WEEKLY_DIR, f"{folder} 周报.md")
    month_file = f"{date_str[:7]} 月度敏捷与学力复盘.md"
    content = f"""---
title: "{folder} 敏捷工程与学力周报"
week: "{week_code}"
date_range: "{monday} ~ {sunday}"
created: {date_str}
updated: {date_str}
tags:
  - weekly
  - review
  - sprint
  - morning-brief
---

# 🚀 {folder} 敏捷工程与学力周报

> 💡 **本周总评**：**{week_code} 周期总结由本地 Agent 根据已归档资料生成。**
>
> 🔗 **所属月度回顾**：{month_file}

---

## 🎯 一、核心战役交付全景

- 

---

## 📊 二、本周待办每日执行矩阵

| 日期 | 星期 | 待办总数 | 已完成 | 完成率 | 达成状态 |
| :--- | :--- | :--- | :--- | :--- | :--- |

---

## 🔗 三、本周关键资产索引
- **本周待办文件夹**：`{folder}/`
- **今日复盘日记**：`{date_str}.md`
"""
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    print(f"✅ 已自动生成本周周报框架: {path}")
    return path


def update_weekly_todo_matrix(
    date_str: str,
    total_count: int,
    completed_count: int,
) -> bool:
    date = common.parse_date(date_str)
    weekly_file = ensure_weekly_report(date_str)
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    rate = f"{completed_count / total_count * 100:.0f}%" if total_count else "0%"
    status = (
        "🟢 优秀" if completed_count >= total_count
        else "🟡 良好" if completed_count >= total_count * 0.7
        else "🔴 待补齐"
    )
    row = (
        f"| {date_str} | {weekdays[date.weekday()]} | {total_count} | "
        f"{completed_count} | {rate} | {status} |"
    )
    try:
        with open(weekly_file, "r", encoding="utf-8") as file:
            content = file.read()
        if f"| {date_str} |" in content:
            content = re.sub(
                rf"^\|\s*{re.escape(date_str)}\s*\|[^\r\n]*$",
                row,
                content,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            header = "| :--- | :--- | :--- | :--- | :--- | :--- |"
            content = content.replace(header, f"{header}\n{row}", 1)
        with open(weekly_file, "w", encoding="utf-8") as file:
            file.write(content)
        print(f"✅ 已将 {date_str} 待办统计更新进周报矩阵: {completed_count}/{total_count} ({rate})")
        return True
    except OSError as exc:
        print(f"⚠️ 更新周报矩阵异常: {exc}")
        return False
