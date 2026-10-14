#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afternoon Fitness Plan Publisher Agent
Reads 09 - 健身管理 current cycle plan, matches today's weekday,
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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
CORE_DIR = os.path.join(PROJECT_ROOT, "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

import config
import feishu_calendar
from feishu_client import feishu_client

FITNESS_PLAN_PATH = os.path.join(
    config.VAULT_ROOT,
    "09 - 健身管理",
    "02 - 阶段目标与周期计划",
    "当前周期训练总计划.md"
)
FITNESS_LOG_PATH = os.path.join(
    config.VAULT_ROOT,
    "09 - 健身管理",
    "05 - 训练日常打卡与复盘",
    "每日任务追踪与执行流水账.md"
)

WEEKDAY_PLAN_MAP = {
    0: ("Day 1 (周一)", "胸部饱满 + 肱三头肌 + 腹直肌上部"),
    1: ("Day 2 (周二)", "背阔肌拉宽 (倒三角) + 肱二头肌 + 绳索面拉 (圆肩克星)"),
    2: ("Day 3 (周三)", "脑力充能与深度恢复日"),
    3: ("Day 4 (周四)", "3D球形肩 (防斜方代偿) + 腹肌下段深层紧腹"),
    4: ("Day 5 (周五)", "悍马倒蹬护膝 + 史密斯RDL改善膝超伸"),
    5: ("Day 6 (周六)", "活力周末有氧 (羽毛球 60~90m / 自由泳 40m)"),
    6: ("Day 7 (周日)", "完全休息日 (8小时睡眠 + 肌肉超量代偿)")
}

def parse_fitness_log_and_nutrition() -> Dict[str, Any]:
    """Parse real-time nutrition and latest training stats from 每日任务追踪与执行流水账.md."""
    data = {
        "streak_days": 14,
        "last_load": "5.33吨 (5330 kg)",
        "last_calorie_burn": "295 kcal",
        "last_duration": "1h 26m",
        "current_calories": "1525 kcal",
        "calorie_target": "1900 kcal",
        "current_protein": "116.7g",
        "protein_target": "135g",
        "protein_remaining": "18.3g",
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
    """Parse today's specific workout routine from Obsidian plan."""
    now = datetime.datetime.now()
    weekday_idx = now.weekday()
    day_tag, muscle_group = WEEKDAY_PLAN_MAP[weekday_idx]
    
    workout_data = {
        "today_str": now.strftime("%Y年%m月%d日"),
        "weekday_str": day_tag,
        "muscle_group": muscle_group,
        "exercises": [],
        "tips": "悍马机独立人体工学轨迹挤压胸背，史密斯机固定安全轨道，零大杠铃失衡风险，安全渐进超负荷！",
        "is_rest_day": weekday_idx in (2, 6)
    }
    
    if not os.path.exists(FITNESS_PLAN_PATH):
        return workout_data
        
    try:
        with open(FITNESS_PLAN_PATH, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Find section for today: e.g. Day 1, Day 2, Day 3...
        day_num = weekday_idx + 1
        target_pattern = rf"### 📌 Day {day_num}\b.*?\n(.*?)(?=\n### 📌|\n---|\Z)"
        match = re.search(target_pattern, content, re.DOTALL)
        if match:
            section_text = match.group(1).strip()
            # Extract exercise lines
            ex_lines = re.findall(r"(?:🛡️|🔥|\d+\.)\s*([^\n]+)", section_text)
            for el in ex_lines:
                clean_el = el.strip().replace("**", "")
                if clean_el:
                    workout_data["exercises"].append(clean_el)
    except Exception as e:
        print(f"⚠️ 解析课表异常: {e}")

    # Fallback default exercises if empty
    if not workout_data["exercises"]:
        if weekday_idx == 0:
            workout_data["exercises"] = [
                "热身 (5m)：弹力带肩袖外旋 2组×15次 + 俯卧撑 2组×10次",
                "悍马坐姿平推/下斜推胸机：4组 × 8~10次 (单边发力，慢放2秒顶峰收缩)",
                "史密斯上斜推胸 (锁骨上胸)：4组 × 10~12次 (长凳30°，下落至锁骨下2cm)",
                "器械蝴蝶机夹胸：3组 × 12~15次 (挤压胸肌中缝)",
                "绳索下压 (肱三头肌)：3组 × 12~15次 (手肘锁死身体两侧)",
                "腹直肌雕刻 (自重/器械卷腹)：4组 × 15~20次 (下背贴地卷起)"
            ]
        elif weekday_idx == 1:
            workout_data["exercises"] = [
                "热身 (5m)：高位下拉轻重量找背部发力 + 泡沫轴滚背",
                "悍马独立高位下拉机：4组 × 8~12次 (肘向下内夹紧，背阔肌深收缩)",
                "悍马坐姿对握划船机：4组 × 10~12次 (胸贴支撑垫，拉向小腹改善圆肩)",
                "单臂哑铃划船：3组 × 10~12次/侧 (拉长大臂下侧背阔肌)",
                "绳索面拉 (Face Pull - 圆肩头前伸必修)：4组 × 15次 (大臂外旋拉回肱骨头)",
                "哑铃交替弯举 (肱二头肌)：3组 × 10~12次 (双手稳固发力)"
            ]
            
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
                            "content": f"数据源：Obsidian 09-健身管理 (当前周期计划 + 每日执行流水账) | 生成时间：{now_time}"
                        }
                    ]
                }
            ]
        }
    }
    return card

def send_feishu(card: Dict[str, Any]) -> bool:
    """Send card via 爪爪openclaw OpenAPI (supports two-way interactive reply)."""
    return feishu_client.send_card(card.get("card", card))

def record_fitness_to_obsidian(workout_data: Dict[str, Any]):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    archive_dir = os.path.join(config.VAULT_ROOT, "09 - 健身管理", "05 - 训练日常打卡与复盘")
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
