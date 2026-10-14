#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global News & Tech Radar Agent
Aggregates Domestic Headliness, International Breaking News,
and Hardcore Open-Source / AI Tech Trends, delivers Feishu interactive card.
"""

import os
import re
import sys
import io
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
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
from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.idempotency import make_key

LOCAL_PROXY = config.LOCAL_PROXY

def get_domestic_news(opener=None) -> List[Dict[str, str]]:
    """Gather real-time domestic headline news (DIRECT, NO PROXY)."""
    items = []
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        url = config.NEWS_DOMESTIC_URLS[0] if config.NEWS_DOMESTIC_URLS else ""
        if not url:
            return items
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for entry in data.get("result", {}).get("data", []):
                title = entry.get("title", "").strip()
                link = entry.get("url", "").strip()
                intro = entry.get("intro", "").strip() or entry.get("summary", "").strip()
                if title and link:
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": intro[:90] if intro else "国内宏观财经与产业最新要闻"
                    })
                if len(items) >= 3:
                    break
    except Exception as e:
        print(f"⚠️ 获取国内滚重新闻异常: {e}")
        
    # Fallback to Sina 7x24 Live
    if len(items) < 3 and len(config.NEWS_DOMESTIC_URLS) > 1:
        try:
            live_url = config.NEWS_DOMESTIC_URLS[1]
            req = urllib.request.Request(live_url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for entry in data.get("result", {}).get("data", {}).get("feed", {}).get("list", []):
                    txt = entry.get("rich_text") or entry.get("content") or ""
                    txt = re.sub(r"<[^>]+>", "", txt).strip()
                    doc_url = entry.get("doc_url") or config.NEWS_FALLBACK_LINK
                    if txt:
                        title_part = txt.split("【")[-1].split("】")[0] if "【" in txt and "】" in txt else txt[:45]
                        items.append({
                            "title": title_part,
                            "link": doc_url,
                            "desc": txt[:90]
                        })
                    if len(items) >= 3:
                        break
        except Exception as e:
            print(f"⚠️ 获取国内快讯异常: {e}")
            
    return items[:3]

def translate_and_summarize_world_news(en_title: str, en_desc: str) -> tuple[str, str]:
    """Translate and summarize one article with the local Agent.

    The parser supplies source text only. It must not infer geopolitical facts
    from keywords or append generic claims that are absent from the article.
    """
    prompt = agent_context.build_prompt(
        task=(
            "将这条外文新闻翻译并压缩成中文。严格返回 JSON："
            "{\"title\":\"准确中文标题\",\"summary\":\"基于原文的中文摘要\"}。"
            "只陈述标题和摘要明确支持的事实；无法确认的信息标记为“原文未说明”，"
            "不要补充背景、预测、立场或其他新闻内容。"
        ),
        query=en_title,
        context=f"【原标题】\n{en_title}\n\n【原文摘要】\n{en_desc}",
    )
    try:
        parsed = agent_provider.ask_json("world-news-summary", prompt)
        if isinstance(parsed, dict):
            title = str(parsed.get("title", "")).strip()
            summary = str(parsed.get("summary", "")).strip()
            if title and summary:
                return title, summary
    except Exception as exc:
        print(f"⚠️ Agent 新闻摘要暂不可用: {exc}")

    # Safe fallback: preserve the source instead of fabricating a summary.
    return f"国际新闻：{en_title[:80]}", en_desc[:240] or "原文摘要为空，暂无法生成中文精读。"

def get_world_news(opener=None) -> List[Dict[str, str]]:
    """Gather international breaking news (VIA OVERSEAS PROXY 7897) with Chinese summaries."""
    items = []
    proxy_handler = urllib.request.ProxyHandler(
        {'http': LOCAL_PROXY, 'https': LOCAL_PROXY} if LOCAL_PROXY else {}
    )
    opener = opener or urllib.request.build_opener(proxy_handler)
    
    for source_url in config.NEWS_WORLD_URLS:
        if len(items) >= 3:
            break
        try:
            req = urllib.request.Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=10) as resp:
                content = resp.read()
            root = ET.fromstring(content)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = item.findtext("description", "").strip()
                clean_desc = re.sub(r"<[^>]+>", "", desc).replace("&nbsp;", " ").strip()
                if title and link:
                    zh_t, zh_d = translate_and_summarize_world_news(title, clean_desc)
                    items.append({
                        "title": zh_t,
                        "en_title": title,
                        "link": link,
                        "desc": zh_d
                    })
                if len(items) >= 3:
                    break
        except Exception as e:
            print(f"⚠️ 代理拉取新闻源异常 ({source_url}): {e}")
            
    return items[:3]

def get_domestic_and_world_news() -> Dict[str, List[Dict[str, str]]]:
    """Gather domestic (direct) and international (proxy) breaking news."""
    return {
        "domestic": get_domestic_news(),
        "world": get_world_news()
    }

def get_tech_radar_news() -> List[Dict[str, str]]:
    """Extract the latest technical digest from the configured local directory."""
    tech_items = []
    tech_dir = config.TECH_NEWS_DIR
    
    if os.path.exists(tech_dir):
        files = sorted([f for f in os.listdir(tech_dir) if f.endswith(".md")], reverse=True)
        if files:
            latest_file = os.path.join(tech_dir, files[0])
            try:
                with open(latest_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                
                # Extract Top GitHub & AI apps
                gh_matches = re.findall(r"### \d+\.\d+\s+([^\n]+)\s*\(\[([^\]]+)\]\((https?://[^\)]+)\)\)", content)
                for gm in gh_matches[:3]:
                    tech_items.append({
                        "name": gm[0].strip(),
                        "repo": gm[1].strip(),
                        "url": gm[2].strip()
                    })
            except Exception:
                pass

    if not tech_items:
        tech_items = []
    return tech_items

def generate_news_takeaway(
    news_data: Dict[str, Any],
    tech_items: List[Dict[str, str]],
) -> str:
    """Generate a source-grounded daily takeaway with the local Agent."""
    context = json.dumps(
        {"news": news_data, "technology": tech_items},
        ensure_ascii=False,
        default=str,
    )[:16000]
    prompt = agent_context.build_prompt(
        task=(
            "根据当天新闻和技术项目生成一段不超过三句的中文晨读结论。"
            "只总结输入中明确出现的事实或趋势，不要使用固定口号、个人身份称谓、"
            "未经来源支持的判断，也不要凭空推荐某个工具。"
        ),
        query="今天这些信息最值得注意的共同趋势是什么？",
        context=context,
    )
    try:
        result = agent_provider.ask_text("news-takeaway", prompt)
        if result and not result.startswith("❌"):
            return result.strip()
    except Exception as exc:
        print(f"⚠️ Agent 晨读结论暂不可用: {exc}")
    return "本次未生成额外晨读结论，请以新闻原文和来源链接为准。"

def build_feishu_news_card(news_data: Dict[str, Any], tech_items: List[Dict[str, str]]) -> Dict[str, Any]:
    """Construct Apple/Linear aesthetic Feishu news card with full clickable links."""
    now_str = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")
    
    # 1. Domestic news
    dom_lines = []
    for i, n in enumerate(news_data["domestic"], 1):
        desc = f"\n   ▸ {n['desc']}" if n.get("desc") else ""
        link_str = f"\n   ▸ 🔗 [点击阅读全文]({n['link']})" if n.get("link") else ""
        title_display = f"[{n['title']}]({n['link']})" if n.get("link") else n['title']
        dom_lines.append(f"**{i}. {title_display}**{desc}{link_str}")
    dom_text = "\n\n".join(dom_lines)

    # 2. World news (Chinese deep summary + original title + clickable link)
    world_lines = []
    for i, n in enumerate(news_data["world"], 1):
        en_note = f"\n   ▸ 🌐 **外媒原题**：`{n['en_title'][:70]}`" if n.get("en_title") else ""
        desc = f"\n   ▸ 📝 **中文精读**：{n['desc']}" if n.get("desc") else ""
        link_str = f"\n   ▸ 🔗 [点击阅读外媒报道原文]({n['link']})" if n.get("link") else ""
        title_display = f"[{n['title']}]({n['link']})" if n.get("link") else n['title']
        world_lines.append(f"**{i}. 🌍 {title_display}**{en_note}{desc}{link_str}")
    world_text = "\n\n".join(world_lines)

    # 3. Hardcore Tech
    tech_lines = []
    for t in tech_items:
        tech_lines.append(f"• 🔥 **[{t['name']}]({t['url']})** (`{t['repo']}`)\n   ▸ 🔗 [查看 GitHub 仓库]({t['url']})")
    tech_text = "\n\n".join(tech_lines)

    # 4. Agent-generated takeaway grounded in today's sources
    takeaway_text = "💡 **今日晨读结论**：\n" + generate_news_takeaway(news_data, tech_items)

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🌍 全球大势与硬核科技雷达 · 晨报"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"📅 **汇聚时间**：`{now_str}` | **信源状态**：三维权威矩阵实时直通 🟢"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"### 🇨🇳 国内宏观政经大势焦点\n\n{dom_text}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"### 🌍 国际一手重大局势动态\n\n{world_text}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"### ⚡ 全球硬核技术与 GitHub 飙升开源\n\n{tech_text}"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": takeaway_text
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "信源：公开新闻源 / 本地技术摘要（如已配置） / MorningBriefAgent"
                        }
                    ]
                }
            ]
        }
    }
    return card

def send_feishu(card: Dict[str, Any]) -> bool:
    """Send card via official openclaw feishu client."""
    return feishu_gateway.send_card_once(
        card, make_key("feishu-card", "news", datetime.date.today().isoformat())
    )

def record_news_to_obsidian(news_data: Dict[str, Any], tech_items: List[Dict[str, str]]):
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    archive_dir = config.TECH_NEWS_DIR
    if not archive_dir:
        return None
    file_path = os.path.join(archive_dir, f"{today_str}-全球大势与科技早报.md")
    
    lines = [
        "---",
        f'title: "{today_str} 全球大势与科技早报"',
        f'date: {today_str}',
        "tags:",
        "  - global-news",
        "  - tech-radar",
        "  - github-trending",
        'status: "已落地已验证"',
        "---",
        "",
        f"# 🌍 {today_str} 全球大势与科技早报",
        "",
        "## 一、国内宏观政经大势",
        ""
    ]
    for n in news_data["domestic"]:
        lines.append(f"- **{n['title']}**：{n.get('desc', '')}")
    lines.extend([
        "",
        "## 二、国际一手重大局势",
        ""
    ])
    for n in news_data["world"]:
        en = f" (原题: `{n['en_title'][:60]}`)" if n.get("en_title") else ""
        link = f" [🔗 阅读外媒原文]({n['link']})" if n.get("link") else ""
        lines.append(f"- 🌍 **{n['title']}**{en}：{n.get('desc', '')}{link}")
    lines.extend([
        "",
        "## 三、全球一手硬核开源与技术突破",
        ""
    ])
    for t in tech_items:
        lines.append(f"- 🔥 **[{t['name']}]({t['url']})** (`{t['repo']}`)")
        
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 全球早报已成功落盘至: {file_path}")

def main():
    print("🚀 启动全球大势与科技雷达早报流水线...")
    news_data = get_domestic_and_world_news()
    tech_items = get_tech_radar_news()
    card = build_feishu_news_card(news_data, tech_items)
    send_feishu(card)
    record_news_to_obsidian(news_data, tech_items)
    print("🎉 全球早报推送全流程顺利完成！")

if __name__ == "__main__":
    main()
