"""Validated application contracts crossing the Agent/business boundary."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ScheduleSlot:
    name: str
    start: str
    end: str
    summary: str
    desc: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScheduleSlot":
        name = str(value.get("name", "")).strip()
        start = str(value.get("start", "")).strip()
        end = str(value.get("end", "")).strip()
        summary = str(value.get("summary", "")).strip()
        for label, time_value in (("start", start), ("end", end)):
            try:
                datetime.datetime.strptime(time_value, "%H:%M")
            except ValueError as exc:
                raise ValueError(f"invalid schedule {label}: {time_value}") from exc
        if not name or not summary:
            raise ValueError("schedule slot requires name and summary")
        return cls(name, start, end, summary, str(value.get("desc", "")).strip())

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name, "start": self.start, "end": self.end,
            "summary": self.summary, "desc": self.desc,
        }


@dataclass(frozen=True)
class AgentPlan:
    date: str
    todos: list[str] = field(default_factory=list)
    schedule_slots: list[ScheduleSlot] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any], default_date: str = "") -> "AgentPlan":
        date = str(value.get("date") or default_date).strip()
        try:
            datetime.date.fromisoformat(date)
        except ValueError as exc:
            raise ValueError(f"invalid plan date: {date}") from exc
        todos = [str(item).strip() for item in value.get("todos", []) if str(item).strip()]
        slots = [
            ScheduleSlot.from_dict(item)
            for item in value.get("schedule_slots", [])
            if isinstance(item, dict)
        ]
        return cls(date=date, todos=todos, schedule_slots=slots)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "todos": list(self.todos),
            "schedule_slots": [slot.to_dict() for slot in self.schedule_slots],
        }
