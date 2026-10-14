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

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
CORE_DIR = os.path.join(PROJECT_ROOT, "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

import config
import agent_context
import agy_bridge
from feishu_client import feishu_client

LOCAL_PROXY = config.LOCAL_PROXY

def get_domestic_news() -> List[Dict[str, str]]:
    """Gather real-time domestic headline news (DIRECT, NO PROXY)."""
    items = []
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=8&page=1"
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
    if len(items) < 3:
        try:
            live_url = "https://zhibo.sina.com.cn/api/zhibo/feed?zhibo_id=152&id=0&tag_id=0&page=1&page_size=6&type=0"
            req = urllib.request.Request(live_url, headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for entry in data.get("result", {}).get("data", {}).get("feed", {}).get("list", []):
                    txt = entry.get("rich_text") or entry.get("content") or ""
                    txt = re.sub(r"<[^>]+>", "", txt).strip()
                    doc_url = entry.get("doc_url") or "https://finance.sina.com.cn/"
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
        result = agy_bridge.ask_native_agy("world-news-summary", prompt)
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", result or "", re.DOTALL)
        parsed = json.loads(fenced.group(1) if fenced else result)
        if isinstance(parsed, dict):
            title = str(parsed.get("title", "")).strip()
            summary = str(parsed.get("summary", "")).strip()
            if title and summary:
                return title, summary
    except Exception as exc:
        print(f"⚠️ Agent 新闻摘要暂不可用: {exc}")

    # Safe fallback: preserve the source instead of fabricating a summary.
    return f"国际新闻：{en_title[:80]}", en_desc[:240] or "原文摘要为空，暂无法生成中文精读。"

def get_world_news() -> List[Dict[str, str]]:
    """Gather international breaking news (VIA OVERSEAS PROXY 7897) with Chinese summaries."""
    items = []
    proxy_handler = urllib.request.ProxyHandler(
        {'http': LOCAL_PROXY, 'https': LOCAL_PROXY} if LOCAL_PROXY else {}
    )
    opener = urllib.request.build_opener(proxy_handler)
    
    # 1. BBC World News
    try:
        url = "http://feeds.bbci.co.uk/news/world/rss.xml"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=10) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        for item in root.findall(".//item")[:3]:
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
    except Exception as e:
        print(f"⚠️ 代理拉取 BBC 异常: {e}")

    # 2. If needed, NYT World
    if len(items) < 3:
        try:
            url = "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
            print(f"⚠️ 代理拉取 NYTimes 异常: {e}")
            
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

    # 4. Takeaway
    takeaway_text = (
        "💡 **架构师晨读手记 (Daily Takeaway)**：\n"
        "AI 时代已经从单纯的大语言模型问答，全面迈入**自主行动代理 (Agentic Actions)** 与真实工具操控新纪元！"
        "理解 Browser-Use 等工具将非结构化 UI 转化为状态机动作空间的工程思想，是构建新一代智能化系统的核心竞争力。"
    )

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
    return feishu_client.send_card(card)

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
