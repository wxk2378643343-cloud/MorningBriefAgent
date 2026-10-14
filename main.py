#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MorningBriefAgent - 统一调度与管理控制台 (CLI)
=====================================================
提供晨报推送、微信复盘、外媒新闻、健身顾问、大盘分析及机器人长驻服务的统一入口。
"""

import sys
import os
import argparse

# 确保项目根目录与子模块在导入搜索路径中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(PROJECT_ROOT, "core")
SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
SERVER_DIR = os.path.join(PROJECT_ROOT, "server")

for p in [PROJECT_ROOT, CORE_DIR, SERVICES_DIR, SERVER_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def run_inspect():
    print("🚀 [MorningBriefAgent] 启动知识库与早间综合简报...")
    from services.inspect_and_brief import main
    main()


def run_chat():
    print("🚀 [MorningBriefAgent] 启动微信聊天多模态深度复盘...")
    from services.chat_digest import main
    main()


def run_news():
    print("🚀 [MorningBriefAgent] 启动全球与科技要闻中文精选...")
    from services.global_news import main
    main()


def run_fitness():
    print("🚀 [MorningBriefAgent] 启动健身训练与热量摄入顾问...")
    from services.fitness_daily import main
    main()


def run_fund():
    print("🚀 [MorningBriefAgent] 启动本地配置与市场摘要...")
    from services.fund_daily_advisor import main
    main()


def run_todo_morning():
    print("🚀 [MorningBriefAgent] 启动早间待办与日程协同推送...")
    from services.daily_todo_service import morning_routine
    morning_routine()


def run_todo_evening():
    print("🚀 [MorningBriefAgent] 启动晚间待办复盘与成果归档...")
    from services.daily_todo_service import evening_routine
    evening_routine()


def run_bot():
    print("🚀 [MorningBriefAgent] 启动飞书机器人后台长驻服务...")
    from server.feishu_bot_server import start_bot
    start_bot()


def main():
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="🌅 MorningBriefAgent 统一智能推送与生活工作助理 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
支持的子命令:
  brief / inspect   本地知识库与晨间综合看板推送
  chat              微信全量私聊/精选群聊多模态深度复盘
  news              早间外媒/科技头条中文精读与直达链接
  fitness           每日健身动作排期与饮食热量指引
  fund              个人持仓快照与公开市场摘要
  todo-morning      早间核心三件事与日程安排同步
  todo-evening      晚间待办完成度复盘与成果流水账归档
  bot / server      飞书机器人长驻服务 (WebSocket 双向交互)

示例:
  python main.py brief
  python main.py chat
  python main.py news
        """
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        default="help",
        help="待执行的业务指令 (brief, chat, news, fitness, fund, todo-morning, todo-evening, bot)"
    )

    args = parser.parse_args()
    cmd = args.command.lower()

    cmd_map = {
        "brief": run_inspect,
        "inspect": run_inspect,
        "chat": run_chat,
        "news": run_news,
        "fitness": run_fitness,
        "fund": run_fund,
        "todo-morning": run_todo_morning,
        "todo-evening": run_todo_evening,
        "bot": run_bot,
        "server": run_bot,
    }

    if cmd in cmd_map:
        cmd_map[cmd]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
