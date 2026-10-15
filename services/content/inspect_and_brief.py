#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Source-grounded, two-pass daily knowledge-base brief."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict

from core.agent import context as agent_context
from core.agent import provider as agent_provider
from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.idempotency import make_key
from core.parsers.email_analyzer import get_latest_high_value_email_digest
from core.pipeline import AgentBatcher, QualityReport, SourceStatus
from core.runtime import config


def collect_brief_data() -> Dict[str, Any]:
    """Collect traceable knowledge-base documents and email summaries."""
    emails = get_latest_high_value_email_digest(
        inbox_dirs=list(config.EMAIL_INBOX_DIRS)
    )
    documents = agent_context.collect_context_documents(
        "今日 待办 计划 项目 目标 日程 邮件 进展",
        max_files=10,
        fallback_dirs=(config.VAULT_ROOT,) if config.VAULT_ROOT else (),
    )
    return {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "documents": documents,
        "context": "\n\n".join(
            f"【来源：{item['path']}】\n{item['excerpt']}" for item in documents
        ),
        "emails": emails,
    }


def evaluate_brief_quality(data: Dict[str, Any]) -> QualityReport:
    documents = data.get("documents", [])
    emails = data.get("emails", [])
    return QualityReport.evaluate(
        (
            SourceStatus(
                "知识库", len(documents), bool(documents), "未读取到可用知识库文档"
            ),
            SourceStatus("邮件", len(emails), bool(emails), "未读取到可用邮件摘要"),
        ),
        minimum_total=1,
        minimum_healthy_sources=1,
    )


def _brief_sources(data: Dict[str, Any]) -> list[dict[str, Any]]:
    sources = [
        {
            "source_id": f"document:{index}",
            "kind": "document",
            "label": str(item.get("path", "")),
            "content": str(item.get("excerpt", "")),
        }
        for index, item in enumerate(data.get("documents", []))
    ]
    sources.extend(
        {
            "source_id": f"email:{index}",
            "kind": "email",
            "label": str(item.get("subject") or item.get("file_path") or "邮件"),
            "content": {
                "date": item.get("date_str", ""),
                "sender": item.get("sender", ""),
                "features": item.get("features", []),
            },
        }
        for index, item in enumerate(data.get("emails", []))
    )
    return sources


def analyze_brief_facts(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract source-grounded facts in complete, size-bounded batches."""
    sources = _brief_sources(data)
    batches = AgentBatcher[dict[str, Any]](18000).partition(
        sources, envelope=lambda values: {"sources": values}
    )
    facts: list[dict[str, Any]] = []
    priorities: list[dict[str, Any]] = []
    risks: list[dict[str, str]] = []
    missing: list[str] = []
    successful_batches = 0
    for batch_index, batch in enumerate(batches, 1):
        valid_source_ids = {item["source_id"] for item in batch}
        prompt = agent_context.build_prompt(
            task=(
                "你是每日简报的事实分析器。仅从输入提取值得关注的事实，不得把旧资料"
                "描述成今天发生。严格输出 JSON："
                "{\"facts\":[{\"statement\":\"事实\",\"source_id\":\"输入中的ID\","
                "\"date_relevance\":\"今日/近期/背景\"}],"
                "\"priorities\":[{\"action\":\"下一步\",\"source_ids\":[\"输入中的ID\"]}],"
                "\"risks\":[{\"text\":\"明确存在的风险或期限\","
                "\"source_id\":\"输入中的ID\"}],\"missing\":[]}。"
                "source_id 必须逐字来自输入；无法关联来源的内容不要输出。"
            ),
            query=f"提取今日简报事实，批次 {batch_index}/{len(batches)}。",
            context=json.dumps({"sources": batch}, ensure_ascii=False),
        )
        try:
            result = agent_provider.ask_json("daily-brief-facts", prompt)
        except Exception as exc:
            print(f"⚠️ 简报事实分析批次 {batch_index} 暂不可用: {exc}")
            missing.append(f"事实分析批次 {batch_index} 未完成")
            continue
        if not isinstance(result, dict):
            missing.append(f"事实分析批次 {batch_index} 返回格式无效")
            continue
        successful_batches += 1
        for item in result.get("facts", []):
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id", "")).strip()
            statement = str(item.get("statement", "")).strip()
            if source_id in valid_source_ids and statement:
                facts.append({
                    "fact_id": f"fact:{len(facts)}",
                    "statement": statement,
                    "source_id": source_id,
                    "date_relevance": str(item.get("date_relevance", "")).strip(),
                })
        for item in result.get("priorities", []):
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "")).strip()
            source_ids = [
                str(value) for value in item.get("source_ids", [])
                if str(value) in valid_source_ids
            ]
            if action and source_ids:
                priorities.append({
                    "action": action,
                    "source_ids": source_ids,
                    "fact_ids": [
                        item["fact_id"] for item in facts
                        if item["source_id"] in source_ids
                    ],
                })
        for item in result.get("risks", []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text", "")).strip()
            source_id = str(item.get("source_id", "")).strip()
            if text and source_id in valid_source_ids:
                risks.append({"text": text, "source_id": source_id})
        missing.extend(
            str(item).strip() for item in result.get("missing", [])
            if str(item).strip()
        )
    return {
        "facts": facts[:12],
        "priorities": priorities[:6],
        "risks": list({
            (item["text"], item["source_id"]): item for item in risks
        }.values())[:6],
        "missing": list(dict.fromkeys(missing))[:6],
        "planned_batches": len(batches),
        "successful_batches": successful_batches,
        "failed_batches": len(batches) - successful_batches,
    }


def _render_brief_fallback(facts: Dict[str, Any]) -> str:
    lines = ["**【今日事实】**"]
    lines.extend(
        f"• {item['statement']}" for item in facts.get("facts", [])
        if item.get("statement")
    )
    lines.append("\n**【优先行动】**")
    lines.extend(
        f"• {item['action']}" for item in facts.get("priorities", [])
        if item.get("action")
    )
    lines.append("\n**【风险与缺口】**")
    lines.extend(
        f"• {item['text']}" for item in facts.get("risks", [])
        if item.get("text")
    )
    lines.extend(f"• {item}" for item in facts.get("missing", []))
    return "\n".join(lines)


def analyze_brief(data: Dict[str, Any]) -> str:
    """Second Agent pass: compose only from the validated fact structure."""
    facts = analyze_brief_facts(data)
    prompt = agent_context.build_prompt(
        task=(
            "把结构化事实编排成简报，但严格输出 JSON："
            "{\"sections\":[{\"title\":\"今日事实\",\"items\":["
            "{\"text\":\"简洁表述\",\"evidence_ids\":[\"fact:0或source_id\"]}]}]}。"
            "每个条目至少引用一个输入中的 fact_id 或 source_id；"
            "不得新增事实、日期或建议。"
        ),
        query="生成今日知识库简报。",
        context=json.dumps(facts, ensure_ascii=False, indent=2),
    )
    try:
        result = agent_provider.ask_json("daily-brief-compose", prompt)
        valid_evidence_ids = {
            item["fact_id"] for item in facts.get("facts", [])
        } | {
            item["source_id"] for item in facts.get("facts", [])
        } | {
            source_id
            for item in facts.get("priorities", [])
            for source_id in item.get("source_ids", [])
        } | {
            item["source_id"] for item in facts.get("risks", [])
        }
        rendered: list[str] = []
        for section in (result or {}).get("sections", []):
            if not isinstance(section, dict):
                continue
            items = []
            for item in section.get("items", []):
                if not isinstance(item, dict):
                    continue
                references = {
                    str(value) for value in item.get("evidence_ids", [])
                }
                text = str(item.get("text", "")).strip()
                if text and references and references <= valid_evidence_ids:
                    items.append(f"• {text}")
            if items:
                rendered.extend([f"**【{section.get('title', '简报')}】**", *items])
        if rendered:
            return "\n".join(rendered)
    except Exception as exc:
        print(f"⚠️ 简报编排暂不可用: {exc}")

    if facts.get("facts"):
        return _render_brief_fallback(facts)
    return "⚠️ 本轮没有通过事实校验的内容，未生成空简报。"


def build_detailed_feishu_card(
    analysis: str,
    quality: QualityReport | None = None,
) -> Dict[str, Any]:
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "🧭 每日知识库简报"},
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": analysis},
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"📡 **数据状态**："
                        f"{quality.status_text() if quality else '已完成采集'}"
                    ),
                },
            },
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "内容来自本地知识库与可用邮件摘要，并经过两阶段 Agent 校验。",
                    }
                ],
            },
        ],
    }


def send_feishu_card(card: Dict[str, Any]) -> bool:
    return feishu_gateway.send_card_once(
        card, make_key("feishu-card", "brief", datetime.date.today().isoformat())
    )


def record_detailed_to_obsidian(analysis: str, generated_at: str) -> str | None:
    output_dir = os.getenv("BRIEF_OUTPUT_DIR", "")
    if not output_dir:
        return None
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{generated_at[:10]}-daily-brief.md"
    path.write_text(
        f"---\ncreated: {generated_at}\ntags: [daily-brief, agent]\n---\n\n"
        f"# Daily Brief ({generated_at[:10]})\n\n{analysis}\n",
        encoding="utf-8",
    )
    return str(path)


def main() -> bool:
    data = collect_brief_data()
    quality = evaluate_brief_quality(data)
    if not quality.ready:
        print(f"⚠️ 简报质量门禁未通过：{'；'.join(quality.issues)}")
        return False
    analysis = analyze_brief(data)
    if not analysis or analysis.startswith("⚠️"):
        print(analysis or "⚠️ 简报内容为空")
        return False
    card = build_detailed_feishu_card(analysis, quality)
    if not send_feishu_card(card):
        print(analysis)
        return False
    record_detailed_to_obsidian(analysis, data["generated_at"])
    return True


if __name__ == "__main__":
    main()
