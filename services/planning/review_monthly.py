"""Monthly review index synchronization."""

from __future__ import annotations

import datetime
import os

from . import review_common as common


def ensure_monthly_report(date_str: str) -> str:
    common.ensure_review_directories()
    date = common.parse_date(date_str)
    month = date.strftime("%Y-%m")
    path = os.path.join(common.MONTHLY_DIR, f"{month} 月度敏捷与学力复盘.md")
    first = date.replace(day=1)
    next_month = (
        first.replace(year=first.year + 1, month=1)
        if first.month == 12
        else first.replace(month=first.month + 1)
    )
    weeks = set()
    cursor = first
    while cursor < next_month:
        code, folder, _, _ = common.get_week_info(cursor)
        weeks.add((code, folder))
        cursor += datetime.timedelta(days=1)
    index_lines = []
    for code, folder in sorted(weeks):
        filename = f"{folder} 周报.md"
        for candidate in os.listdir(common.WEEKLY_DIR):
            if candidate.startswith(code) and candidate.endswith(".md"):
                filename = candidate
                break
        index_lines.append(f"- 🚀 **{code}**：{filename} · 待办流水：{folder}/")
    index = "\n".join(index_lines)
    if not os.path.exists(path):
        content = f"""---
title: "{month} 月度敏捷与学力全景复盘"
month: "{month}"
created: {date_str}
updated: {date_str}
tags:
  - monthly
  - review
  - agent-generated
---

# 🌕 {month} 月度敏捷与学力全景复盘

> 💡 **月度总评**：由本地 Agent 根据已归档资料生成。

---

## 📅 一、全月敏捷周报穿透索引

{index}

---

## 🎯 二、月度核心里程碑交付

由 Agent 从归档资料中提取。

---

## 📊 三、全月执行健康度总览

| 维度 | 月度目标 | 实际达成 | 健康度 |
| :--- | :--- | :--- | :--- |
| 目标完成情况 | 由 Agent 统计 | 持续统计中 | 🟡 待分析 |
| 重要进展 | 由 Agent 提取 | 持续统计中 | 🟡 待分析 |
| 待办完成率 | 自动统计 | 持续统计中 | 🟡 待分析 |
| 风险与阻塞 | 由 Agent 提取 | 持续统计中 | 🟡 待分析 |
"""
    else:
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        content = common.replace_markdown_section(
            content, "## 📅 一、全月敏捷周报穿透索引", index
        )
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    print(f"✅ 已刷新月度复盘周报索引: {path}")
    return path
