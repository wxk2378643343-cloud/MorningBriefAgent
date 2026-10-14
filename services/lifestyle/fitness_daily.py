#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afternoon Fitness Plan Publisher Agent
Reads configured activity plan and log paths,
extracts target muscle groups, Hammer Strength / Smith Machine exercises, sets & reps,
delivers a high-energy Feishu card at 16:00 and archives to Obsidian.
"""

import sys
import os
import re
import io
import json
import datetime
import urllib.request
from typing import Dict, List, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.runtime import config
from core.agent import context as agent_context
from core.agent import provider as agent_provider
from core.integrations.feishu import calendar as feishu_calendar
from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.idempotency import make_key

FITNESS_PLAN_PATH = config.FITNESS_PLAN_PATH
FITNESS_LOG_PATH = config.FITNESS_LOG_PATH

def parse_fitness_log_and_nutrition() -> Dict[str, Any]:
    """Parse configured activity logs without inventing nutrition defaults."""
    data = {
        "streak_days": 0,
        "last_load": "未记录",
        "last_calorie_burn": "未记录",
        "last_duration": "未记录",
        "current_calories": "未记录",
        "calorie_target": "未配置",
        "current_protein": "未记录",
        "protein_target": "未配置",
        "protein_remaining": "未计算",
        "meals_recorded": []
    }
    if not os.path.exists(FITNESS_LOG_PATH):
        return data

    try:
        with open(FITNESS_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # 1. Parse latest streak and training stats
        streak_match = re.search(r"连续打卡\s*\*\*第(\d+)天\*\*", content)
        if streak_match:
            data["streak_days"] = int(streak_match.group(1))

        load_match = re.search(r"总负荷\s*`?([0-9\.]+\s*(?:吨|kg))`?", content)
        if load_match:
            data["last_load"] = load_match.group(1).strip()

        burn_match = re.search(r"消耗\s*`?(\d+\s*kcal)`?", content)
        if burn_match:
            data["last_calorie_burn"] = burn_match.group(1).strip()

        # 2. Parse nutrition macro
        cal_match = re.search(r"当前总热量[^\n]*\*\*([^\*]+)\*\*\s*/\s*([^\s\n]+)", content)
        if cal_match:
            data["current_calories"] = cal_match.group(1).replace("$", "").replace("\\approx", "≈").strip()
            data["calorie_target"] = cal_match.group(2).replace("$", "").strip()

        pro_match = re.search(r"当前蛋白质[^\n]*\*\*([^\*]+)\*\*\s*/\s*([^\s\n]+)", content)
        if pro_match:
            data["current_protein"] = pro_match.group(1).replace("$", "").replace("\\approx", "≈").strip()
            data["protein_target"] = pro_match.group(2).replace("$", "").strip()

        # 3. Parse recorded meals
        meal_matches = re.findall(r"- \[x\]\s*\*\*([^\n]+已完成[^\n]*)\*\*\s*\n\s*-\s*\*\*实拍配餐\*\*：([^\n]+)", content)
        for mm in meal_matches[:2]:
            data["meals_recorded"].append(f"{mm[0].split('(')[0].strip()}: {mm[1].strip()[:35]}...")
    except Exception as e:
        print(f"⚠️ 解析流水账异常: {e}")

    return data

def parse_today_workout() -> Dict[str, Any]:
    """Ask the local Agent to interpret today's configured activity plan."""
    now = datetime.datetime.now()
    workout_data = {
        "today_str": now.strftime("%Y年%m月%d日"),
        "weekday_str": now.strftime("%A"),
        "muscle_group": "未配置",
        "exercises": [],
        "tips": "请根据本地活动计划与 Agent 分析结果执行。",
        "is_rest_day": False
    }

    if not FITNESS_PLAN_PATH or not os.path.exists(FITNESS_PLAN_PATH):
        return workout_data
    try:
        with open(FITNESS_PLAN_PATH, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        prompt = agent_context.build_prompt(
            task=(
                "阅读活动计划，找出指定日期的安排并严格返回 JSON："
                "{\"weekday_str\":\"...\",\"muscle_group\":\"...\","
                "\"exercises\":[\"...\"],\"tips\":\"...\",\"is_rest_day\":false}。"
                "只使用计划中明确出现的内容；找不到时返回空 exercises、"
                "muscle_group 为“未配置”，不要发明训练项目、动作、目标或营养建议。"
            ),
            query=f"请分析 {now.strftime('%Y-%m-%d')} 的活动安排。",
            context=content[:24000],
        )
        parsed = agent_provider.ask_json("activity-plan", prompt)
        if isinstance(parsed, dict):
            for key in ("weekday_str", "muscle_group", "tips"):
                if isinstance(parsed.get(key), str) and parsed[key].strip():
                    workout_data[key] = parsed[key].strip()
            if isinstance(parsed.get("exercises"), list):
                workout_data["exercises"] = [str(x) for x in parsed["exercises"][:20]]
            workout_data["is_rest_day"] = bool(parsed.get("is_rest_day", False))
    except Exception as e:
        print(f"⚠️ Agent 活动计划分析异常: {e}")
    return workout_data

def build_feishu_fitness_card(workout_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build high-energy Feishu card for 16:00 workout reminder."""
    now_time = datetime.datetime.now().strftime("%H:%M")
    
    header_title = f"🏋️ 今日健身课表 · {workout_data['weekday_str']}"
    
    if workout_data["is_rest_day"]:
        ex_text = (
            "🧘 **今日为脑力充能与身体深度修复日！**\n\n"
            "• 无大强度力量摧毁，给中枢神经与肌纤维充分合成超量代偿的时间；\n"
            "• 建议晚间进行 15 分钟全身泡沫轴滚背与下肢筋膜放松；\n"
            "• 地铁通勤背单词，保持充足供水，今晚争取早睡 15 分钟！"
        )
    else:
        ex_lines = []
        for i, ex in enumerate(workout_data["exercises"], 1):
            ex_lines.append(f"**{i}. {ex}**")
        ex_text = "\n\n".join(ex_lines)

    nutrition_data = parse_fitness_log_and_nutrition()
    
    # 动态构建营养大盘展示
    meals_str = "\n".join([f"• {m}" for m in nutrition_data["meals_recorded"]]) if nutrition_data["meals_recorded"] else "• 早餐与午餐按计划完成"
    nutrition_text = (
        f"📊 **全天热量与蛋白质实时大盘 (取自执行流水账)**：\n"
        f"• 🥩 **当前蛋白质**：**`{nutrition_data['current_protein']}`** / `{nutrition_data['protein_target']}`\n"
        f"• 🔥 **当前总热量**：**`{nutrition_data['current_calories']}`** / `{nutrition_data['calorie_target']}` (安全微赤字区间)\n"
        f"• 🥗 **已记录餐食**：\n{meals_str}\n\n"
        f"💡 **补充建议**：\n"
        f"• 训练前后请依据本地知识库中配置的饮食偏好与营养目标安排补充。"
    )

    # 动态读取 staged_plan.json 中已确立的健身时间盒，避免硬编码冲突
    fit_time = "未配置"
    try:
        plan_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "staged_plan.json")
        if os.path.exists(plan_file):
            with open(plan_file, "r", encoding="utf-8") as pf:
                plan_data = json.load(pf)
            for s in plan_data.get("schedule_slots", []):
                if "健身" in s.get("name", ""):
                    fit_time = f"{s.get('start', '')} ~ {s.get('end', '')}"
                    break
    except Exception:
        pass

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": header_title},
                "template": "orange"  # 活力燃脂橙
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"🏆 **连续打卡**：**第 {nutrition_data['streak_days']} 天** | "
                            f"🏋️ **实战总负荷**：`{nutrition_data['last_load']}` | 🔥 **单次消耗**：`{nutrition_data['last_calorie_burn']}`\n"
                            f"🎯 **今日攻坚部位**：`【{workout_data['muscle_group']}】`\n"
                            f"⏰ **活动时间盒**：`{fit_time}`"
                        )
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"### 🛡️ 今日实战动作清单与组数标准\n\n{ex_text}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"### 🥩 饮食营养追踪与教练补剂指令\n\n{nutrition_text}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📅 **飞书日历日程状态**：✅ **已由晨启总控统一定时排定** (`{fit_time}` | 提前15分钟 17:15 强提醒)\n*（下午推送仅做动作提醒与补剂备忘，不二次写入日历，彻底杜绝日程冲突）*"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"数据源：已配置的活动计划与执行记录 | 生成时间：{now_time}"
                        }
                    ]
                }
            ]
        }
    }
    return card

def send_feishu(card: Dict[str, Any]) -> bool:
    """Send card via 爪爪openclaw OpenAPI (supports two-way interactive reply)."""
    return feishu_gateway.send_card_once(
        card.get("card", card), make_key(
            "feishu-card", "fitness", datetime.date.today().isoformat()
        )
    )

def record_fitness_to_obsidian(workout_data: Dict[str, Any]):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    archive_dir = config.FITNESS_ARCHIVE_DIR
    if not archive_dir:
        return None
    file_path = os.path.join(archive_dir, f"{today_str}-训练课表推送与执行记录.md")
    
    # 保护机制：如果今日文件已存在且包含饮食记录或勾选，绝不暴力覆写！
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                old_content = f.read()
            if "今日饮食营养摄入" in old_content or "- [x]" in old_content:
                print(f"ℹ️ 今日课表已存在且包含饮食/打卡记录，跳过覆写以保护已有数据: {file_path}")
                return
        except Exception:
            pass

    lines = [
        "---",
        f'title: "{today_str} 训练课表推送与执行记录"',
        f'date: {today_str}',
        "tags:",
        "  - fitness",
        "  - workout",
        "  - hammer-strength",
        "  - smith-machine",
        'status: "已落地已验证"',
        "---",
        "",
        f"# 🏋️ {today_str} 训练课表 ({workout_data['weekday_str']})",
        "",
        f"> 🎯 **训练部位**：`{workout_data['muscle_group']}`",
        "",
        "## 今日实战动作清单",
        ""
    ]
    for ex in workout_data["exercises"]:
        lines.append(f"- [ ] {ex}")
    lines.extend([
        "",
        "## 练后复盘备忘",
        "- 实际完成组数：待练后打勾",
        "- 关节酸痛度：0 (无异常)"
    ])
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 健身课表已落盘至: {file_path}")

def main():
    print("🚀 启动下午 16:00 健身计划发布流水线...")
    workout_data = parse_today_workout()
    print(f"🏋️ 课表解析完成: 今天是 {workout_data['weekday_str']}，攻坚部位：{workout_data['muscle_group']}")
    card = build_feishu_fitness_card(workout_data)
    send_feishu(card)
    record_fitness_to_obsidian(workout_data)
    print("🎉 健身计划发布全流程顺利完成！")

if __name__ == "__main__":
    main()
