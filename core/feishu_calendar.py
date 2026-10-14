#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feishu Calendar Integration & Silent Auto-Scheduling Engine
1. OpenAPI Silent Auto-Add: Background API writes directly to Feishu Calendar, 0 clicks needed.
2. Time-Boxing Schedule: Uses caller-provided time blocks,
   fitness (18:30~20:00), and evening deep study (20:30~23:30).
3. Automatic Attendees & Alarms: Adds user as attendee with 15-minute advance popup/push notification.
4. AppLink Fallback: Generates 1-click Feishu client deep link for quick card view.
"""

import os
import sys
import io
import json
import urllib.request
import urllib.parse
import datetime
from typing import Dict, Any, Optional, List, Tuple

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

try:
    from . import config
except ImportError:
    import config

class FeishuCalendarManager:
    """Manages Feishu Calendar via OpenAPI v4."""
    
    def __init__(self):
        self.app_id = getattr(config, 'FEISHU_APP_ID', '')
        self.app_secret = getattr(config, 'FEISHU_APP_SECRET', '')
        self.user_open_id = getattr(config, 'FEISHU_USER_OPEN_ID', '')
        self._token = None
        self._token_expire = 0
        self._calendar_id = None
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        
    def get_token(self) -> Optional[str]:
        """Fetch or refresh tenant_access_token."""
        now_ts = datetime.datetime.now().timestamp()
        if self._token and now_ts < self._token_expire - 60:
            return self._token
            
        if not self.app_id or not self.app_secret:
            return None
            
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with self._opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    self._token = data.get("tenant_access_token")
                    self._token_expire = now_ts + data.get("expire", 7200)
                    return self._token
                else:
                    print(f"⚠️ 获取飞书 Token 失败: {data.get('msg')}")
        except Exception as e:
            print(f"⚠️ 请求飞书 Token 异常: {e}")
        return None

    def get_calendar_id(self) -> Optional[str]:
        """Get or initialize the bot's primary calendar."""
        if self._calendar_id:
            return self._calendar_id
            
        token = self.get_token()
        if not token:
            return None
            
        url = "https://open.feishu.cn/open-apis/calendar/v4/calendars"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with self._opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    cal_list = data.get("data", {}).get("calendar_list", [])
                    if cal_list:
                        self._calendar_id = cal_list[0].get("calendar_id")
                        self._ensure_acl()
                        return self._calendar_id
        except Exception as e:
            print(f"⚠️ 获取日历列表异常: {e}")
        return None

    def _ensure_acl(self):
        """Ensure the user has writer access to this calendar."""
        token = self.get_token()
        if not token or not self._calendar_id or not self.user_open_id:
            return
            
        url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{self._calendar_id}/acls"
        body = json.dumps({
            "role": "writer",
            "scope": {"type": "user", "user_id": self.user_open_id}
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        )
        try:
            with self._opener.open(req, timeout=10) as resp:
                pass # ACL ensured
        except Exception:
            pass

    def list_day_events(self, target_date: datetime.date) -> List[Dict[str, Any]]:
        """List active, non-cancelled events for target date."""
        token = self.get_token()
        cal_id = self.get_calendar_id()
        if not token or not cal_id:
            return []

        start_ts = str(int(datetime.datetime.combine(target_date, datetime.time.min).timestamp()))
        end_ts = str(int(datetime.datetime.combine(target_date, datetime.time.max).timestamp()))
        url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{cal_id}/events?start_time={start_ts}&end_time={end_ts}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with self._opener.open(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("data", {}).get("items", [])
                # Return only active events with summary
                return [it for it in items if it.get("status") != "cancelled" and it.get("summary")]
        except Exception as e:
            print(f"⚠️ 查询日历事件异常: {e}")
            return []

    def create_silent_event(
        self,
        summary: str,
        start_dt: datetime.datetime,
        end_dt: datetime.datetime,
        description: str = "",
        reminder_minutes: int = 15,
        check_duplicate: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Silently create a calendar event in Feishu with strict check-before-add deduplication guard.
        If a similar/overlapping event already exists, reuses it immediately to prevent duplicate clutter!
        """
        token = self.get_token()
        cal_id = self.get_calendar_id()
        if not token or not cal_id:
            return False, None

        start_ts_int = int(start_dt.timestamp())
        end_ts_int = int(end_dt.timestamp())
        start_ts = str(start_ts_int)
        end_ts = str(end_ts_int)

        # 🛡️ 核心防重铁律：加日程先检查！
        if check_duplicate:
            existing = self.list_day_events(start_dt.date())
            for ev in existing:
                ev_start = int(ev.get("start_time", {}).get("timestamp", 0))
                ev_end = int(ev.get("end_time", {}).get("timestamp", 0))
                ev_summary = ev.get("summary", "")

                # 1. 相同起止时间
                same_time = (ev_start == start_ts_int and ev_end == end_ts_int)
                # 2. 时间窗口重叠
                time_overlap = max(0, min(end_ts_int, ev_end) - max(start_ts_int, ev_start)) > 1800 # 重叠超30分钟
                # 3. 主题关键词相似
                keywords = ["晨读", "健身", "跑步", "晚学", "攻坚", "工作"]
                matched_kw = any(kw in summary and kw in ev_summary for kw in keywords)

                if same_time or (time_overlap and matched_kw) or summary == ev_summary:
                    print(f"[日程先检护栏] 检测到已存在同类日程 '{ev_summary}' ({ev.get('event_id')})，直接复用，拒绝重复新增！")
                    return True, ev.get("event_id")

        event_url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{cal_id}/events"
        event_payload = {
            "summary": summary,
            "description": description,
            "start_time": {"timestamp": start_ts},
            "end_time": {"timestamp": end_ts},
            "reminders": [{"minutes": reminder_minutes}],
            "visibility": "default"
        }

        req = urllib.request.Request(
            event_url,
            data=json.dumps(event_payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        )

        try:
            with self._opener.open(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("code") == 0:
                    event_id = res.get("data", {}).get("event", {}).get("event_id")
                    # Add user as attendee to show on personal calendar and ring notification
                    if event_id and self.user_open_id:
                        att_url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{cal_id}/events/{event_id}/attendees?user_id_type=open_id"
                        att_payload = {
                            "attendees": [{"type": "user", "is_optional": False, "user_id": self.user_open_id}],
                            "need_notification": True
                        }
                        req_att = urllib.request.Request(
                            att_url,
                            data=json.dumps(att_payload).encode("utf-8"),
                            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
                        )
                        with self._opener.open(req_att, timeout=10) as att_resp:
                            pass
                    return True, event_id
                else:
                    print(f"⚠️ 静默创建日程失败: {res.get('msg')}")
        except Exception as e:
            print(f"⚠️ 静默创建日程网络异常: {e}")

        return False, None

    def clean_day_events(self, target_date: datetime.date):
        """Clean today's existing events to avoid duplicates when rescheduling."""
        token = self.get_token()
        cal_id = self.get_calendar_id()
        if not token or not cal_id:
            return

        active_items = self.list_day_events(target_date)
        for it in active_items:
            ev_id = it.get("event_id")
            if ev_id:
                del_url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{cal_id}/events/{ev_id}"
                del_req = urllib.request.Request(del_url, headers={"Authorization": f"Bearer {token}"}, method="DELETE")
                try:
                    with self._opener.open(del_req, timeout=5):
                        print(f"🗑️ 已清理旧日程: {it.get('summary')} ({ev_id})")
                except Exception:
                    pass

    def delete_event(self, event_id: str) -> bool:
        """Delete a single event by event_id."""
        token = self.get_token()
        cal_id = self.get_calendar_id()
        if not token or not cal_id or not event_id:
            return False

        del_url = f"https://open.feishu.cn/open-apis/calendar/v4/calendars/{cal_id}/events/{event_id}"
        del_req = urllib.request.Request(del_url, headers={"Authorization": f"Bearer {token}"}, method="DELETE")
        try:
            with self._opener.open(del_req, timeout=5):
                print(f"🗑️ 已成功删除日历日程: {event_id}")
                return True
        except Exception as e:
            print(f"⚠️ 删除日历日程异常 ({event_id}): {e}")
            return False

# Singleton manager
calendar_mgr = FeishuCalendarManager()

def build_calendar_applink(
    summary: str,
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    description: str = "",
    need_notification: bool = True
) -> str:
    """Build Feishu AppLink Schema URL."""
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    params = {
        "summary": summary,
        "startTime": str(start_ms),
        "endTime": str(end_ms),
        "needNotification": "true" if need_notification else "false"
    }
    if description:
        params["description"] = description
    query_str = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"https://applink.feishu.cn/client/calendar/event/create?{query_str}"

def schedule_silent_fitness(
    target_date: datetime.date,
    workout_name: str,
    exercises_desc: str,
    start_time: str = "",
    end_time: str = "",
) -> Dict[str, Any]:
    """
    Schedule an activity using caller-provided times.

    The function remains available for backwards compatibility, but no
    personal venue, routine, or nutrition assumption is embedded here.
    """
    if not start_time or not end_time:
        return {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "📅 未创建活动：请先在本地知识库或 Agent 计划中配置开始与结束时间。"},
        }
    try:
        start_clock = datetime.datetime.strptime(start_time, "%H:%M").time()
        end_clock = datetime.datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        return {
            "tag": "div",
            "text": {"tag": "lark_md", "content": "📅 未创建活动：时间格式应为 HH:MM。"},
        }
    start_dt = datetime.datetime.combine(target_date, start_clock)
    end_dt = datetime.datetime.combine(target_date, end_clock)
    summary = workout_name or "Agent 安排的活动"
    desc = f"活动：{summary}\n时间：{start_time} ~ {end_time}\n\n{exercises_desc}".strip()
    
    # 1. Execute silent creation via OpenAPI
    success, ev_id = calendar_mgr.create_silent_event(summary, start_dt, end_dt, desc, reminder_minutes=15)
    
    applink = build_calendar_applink(summary, start_dt, end_dt, desc, need_notification=True)
    
    if success:
        status_text = f"✅ **已全自动静默写入飞书日历**（时段：{start_time}~{end_time}）"
        btn_text = "📅 查看/编辑日历日程"
    else:
        status_text = f"📅 **日程规划**（时段：{start_time}~{end_time}）"
        btn_text = "📅 一键添加到飞书日历"
        
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"{status_text}\n[👉 {btn_text}]({applink})"
        }
    }

def schedule_silent_study(
    target_date: datetime.date,
    morning_tasks: str = "",
    evening_tasks: str = "",
    morning_start: str = "",
    morning_end: str = "",
    evening_start: str = "",
    evening_end: str = "",
) -> Dict[str, Any]:
    """
    Schedule up to two caller-provided focus blocks.

    Defaults are intentionally empty: goals and time blocks belong to the
    configured knowledge base or Agent output, not to source code.
    """
    blocks = [
        ("focus-1", morning_tasks, morning_start, morning_end),
        ("focus-2", evening_tasks, evening_start, evening_end),
    ]
    links = []
    created = 0
    for label, task, start_text, end_text in blocks:
        if not start_text or not end_text:
            continue
        try:
            start_clock = datetime.datetime.strptime(start_text, "%H:%M").time()
            end_clock = datetime.datetime.strptime(end_text, "%H:%M").time()
        except ValueError:
            continue
        start_dt = datetime.datetime.combine(target_date, start_clock)
        end_dt = datetime.datetime.combine(target_date, end_clock)
        summary = task or label
        desc = f"任务：{task}\n时间：{start_text} ~ {end_text}".strip()
        success, _ = calendar_mgr.create_silent_event(summary, start_dt, end_dt, desc, reminder_minutes=10)
        created += int(success)
        links.append(f"• **{summary} ({start_text}~{end_text})** [👉 查看日程]({build_calendar_applink(summary, start_dt, end_dt, desc)})")

    if not links:
        cal_status = "📅 未创建时间块：请先在本地知识库或 Agent 计划中配置时间与任务。"
    else:
        state = "✅ 已写入飞书日历" if created == len(links) else "📅 已生成日历链接"
        cal_status = f"{state}：\n" + "\n".join(links)
    
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": cal_status
        }
    }
