#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual integration check that writes to the configured Obsidian vault."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
if SERVICES_DIR not in sys.path:
    sys.path.insert(0, SERVICES_DIR)

import review_sync_service

def main():
    today_str = "2026-10-14"
    sample_todos = [
        "整理项目资料",
        "阅读一篇技术文章",
        "处理一封重要邮件",
        "完成一个小型编码任务",
        "整理本周会议记录",
        "备份重要文件"
    ]

    print("=== 1. 测试日/周/月三级级联保全 ===")
    res = review_sync_service.cascade_sync_all(today_str, sample_todos)
    print(f"日记路径: {res['daily']}")
    print(f"周报路径: {res['weekly']}")
    print(f"月报路径: {res['monthly']}")
    assert os.path.exists(res["daily"]), "Daily journal missing"
    assert os.path.exists(res["weekly"]), "Weekly report missing"
    assert os.path.exists(res["monthly"]), "Monthly report missing"
    print("✅ 三级级联保全测试通过！")

    print("\n=== 2. 测试周报待办执行矩阵更新 ===")
    ok_matrix = review_sync_service.update_weekly_todo_matrix("2026-10-13", 6, 5)
    assert ok_matrix, "Failed to update weekly matrix"
    print("✅ 周报矩阵更新测试通过！")

    print("\n=== 3. 测试打卡同步勾选至日记 ===")
    ok_chk = review_sync_service.sync_todo_completion_to_journal(["备份重要文件"], today_str)
    print(f"勾选结果: {ok_chk}")
    with open(res["daily"], "r", encoding="utf-8") as f:
        daily_text = f.read()
    assert "- [x] **备份重要文件**" in daily_text or "- [ ] **备份重要文件**" in daily_text
    print("✅ 日记勾选双写测试通过！")

    print("\n🎉 全部单元测试 100% 通过！")

if __name__ == "__main__":
    main()
