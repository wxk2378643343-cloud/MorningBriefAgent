"""Archive the local AGY transcript into daily Markdown files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime import config


def archive_transcript(
    transcript: str,
    output_dir: str,
    *,
    day: str | None = None,
) -> list[str]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    source = Path(transcript)
    if not source.is_file():
        return []
    with source.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            created = str(record.get("created_at", ""))
            record_day = created[:10]
            if len(record_day) == 10 and (day is None or record_day == day):
                grouped[record_day].append(record)

    target_root = Path(output_dir)
    target_root.mkdir(parents=True, exist_ok=True)
    written = []
    for record_day, records in sorted(grouped.items()):
        path = target_root / f"{record_day}-AGY对话详细日志.md"
        lines = [
            "---",
            "generated_by: MorningBriefAgent",
            f"date: {record_day}",
            "source: AGY transcript.jsonl",
            "status: raw-transcript-archive",
            "---",
            "",
            f"# AGY 对话详细日志 ({record_day})",
            "",
            "> 本文件保留 AGY 的模型回复、工具调用和系统事件，便于复盘。"
            "其中工具输出可能包含本地文件内容，请勿上传到公共仓库。",
            "",
        ]
        for record in records:
            timestamp = str(record.get("created_at", ""))
            source_name = str(record.get("source", "UNKNOWN"))
            record_type = str(record.get("type", "UNKNOWN"))
            status = str(record.get("status", ""))
            lines.extend([
                f"## {timestamp} · {source_name} / {record_type} {status}",
                "",
            ])
            for key in ("content", "thinking"):
                value = record.get(key)
                if value:
                    lines.extend([f"### {key}", "", str(value), ""])
            tool_calls = record.get("tool_calls")
            if tool_calls:
                lines.extend([
                    "### tool_calls",
                    "",
                    "```json",
                    json.dumps(tool_calls, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ])
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(str(path))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive AGY transcript by day")
    parser.add_argument("--day", help="Only archive YYYY-MM-DD")
    parser.add_argument(
        "--transcript",
        default=str(
            Path(config.AGY_BRAIN_DIR)
            / config.AGY_CONVERSATION_ID
            / ".system_generated"
            / "logs"
            / "transcript.jsonl"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=(
            config.AGY_ARCHIVE_DIR
            or str(
                Path(config.OBSIDIAN_VAULT_ROOT)
                / "12 - 工作情况记录"
                / "AGY对话日志"
            )
        ),
    )
    args = parser.parse_args()
    written = archive_transcript(args.transcript, args.output_dir, day=args.day)
    print(f"已归档 {len(written)} 个 AGY 日志文件")
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
