"""Deterministic collection, normalization and freshness checks for news."""

from __future__ import annotations

import datetime
import email.utils
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable


def feed_entries(content: bytes, source_url: str = "") -> list[dict[str, str]]:
    root = ET.fromstring(content)
    entries: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        entries.append({
            "title": (item.findtext("title", "") or "").strip(),
            "link": (item.findtext("link", "") or "").strip(),
            "desc": re.sub(
                r"<[^>]+>", "", item.findtext("description", "") or ""
            ).replace("&nbsp;", " ").strip(),
            "published": (
                item.findtext("pubDate", "")
                or item.findtext("{http://purl.org/dc/elements/1.1/}date", "")
                or ""
            ).strip(),
            "source_url": source_url,
        })
    atom_ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{atom_ns}entry"):
        link_node = entry.find(f"{atom_ns}link")
        entries.append({
            "title": (entry.findtext(f"{atom_ns}title", "") or "").strip(),
            "link": (link_node.get("href", "") if link_node is not None else "").strip(),
            "desc": re.sub(
                r"<[^>]+>", "",
                entry.findtext(f"{atom_ns}summary", "")
                or entry.findtext(f"{atom_ns}content", "")
                or "",
            ).strip(),
            "published": (
                entry.findtext(f"{atom_ns}updated", "")
                or entry.findtext(f"{atom_ns}published", "")
                or ""
            ).strip(),
            "source_url": source_url,
        })
    return [item for item in entries if item["title"] and item["link"]]


def parse_published(value: Any) -> datetime.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        try:
            return datetime.datetime.fromtimestamp(
                numeric, tz=datetime.timezone.utc
            )
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def is_fresh(
    item: dict[str, Any],
    *,
    now: datetime.datetime | None = None,
    max_age_hours: int = 48,
) -> bool:
    published = parse_published(item.get("published"))
    if published is None:
        return False
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    age = current.astimezone(datetime.timezone.utc) - published
    return datetime.timedelta(hours=-1) <= age <= datetime.timedelta(
        hours=max_age_hours
    )


def deduplicate(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_links: set[str] = set()
    for item in items:
        title_key = re.sub(
            r"\W+", "", str(item.get("title") or item.get("name") or "").lower()
        )
        link_key = str(item.get("link") or item.get("url") or "").split("?")[0]
        if (
            not title_key
            or title_key in seen_titles
            or (link_key and link_key in seen_links)
        ):
            continue
        seen_titles.add(title_key)
        if link_key:
            seen_links.add(link_key)
        output.append(item)
    return output


def collect_domestic(
    urls: Iterable[str],
    *,
    fallback_link: str,
    opener=None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    urls = tuple(urls)
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
    items: list[dict[str, Any]] = []
    if urls:
        try:
            request = urllib.request.Request(
                urls[0], headers={"User-Agent": "Mozilla/5.0"}
            )
            with opener.open(request, timeout=6) as response:
                data = json.loads(response.read().decode("utf-8"))
            for entry in data.get("result", {}).get("data", []):
                title = str(entry.get("title", "")).strip()
                link = str(entry.get("url", "")).strip()
                if title and link:
                    items.append({
                        "title": title,
                        "link": link,
                        "desc": str(
                            entry.get("intro") or entry.get("summary") or ""
                        ).strip(),
                        "published": (
                            entry.get("ctime") or entry.get("create_time")
                            or entry.get("date") or entry.get("time") or ""
                        ),
                        "source_url": urls[0],
                    })
        except Exception as exc:
            print(f"⚠️ 获取国内滚动新闻异常: {exc}")
    if len(items) < 3 and len(urls) > 1:
        try:
            request = urllib.request.Request(
                urls[1], headers={"User-Agent": "Mozilla/5.0"}
            )
            with opener.open(request, timeout=6) as response:
                data = json.loads(response.read().decode("utf-8"))
            feed = data.get("result", {}).get("data", {}).get("feed", {}).get("list", [])
            for entry in feed:
                text = re.sub(
                    r"<[^>]+>", "", str(
                        entry.get("rich_text") or entry.get("content") or ""
                    )
                ).strip()
                if text:
                    items.append({
                        "title": (
                            text.split("【")[-1].split("】")[0]
                            if "【" in text and "】" in text else text[:45]
                        ),
                        "link": entry.get("doc_url") or fallback_link,
                        "desc": text[:240],
                        "published": (
                            entry.get("create_time") or entry.get("ctime")
                            or entry.get("date") or entry.get("time") or ""
                        ),
                        "source_url": urls[1],
                    })
        except Exception as exc:
            print(f"⚠️ 获取国内快讯异常: {exc}")
    return deduplicate(items)[:limit]


def collect_feed_items(
    urls: Iterable[str],
    *,
    proxy: str = "",
    opener=None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    opener = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler(
            {"http": proxy, "https": proxy} if proxy else {}
        )
    )
    items: list[dict[str, Any]] = []
    for source_url in urls:
        try:
            request = urllib.request.Request(
                source_url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with opener.open(request, timeout=10) as response:
                items.extend(feed_entries(response.read(), source_url))
        except Exception as exc:
            print(f"⚠️ 拉取新闻源异常 ({source_url}): {exc}")
        if len(deduplicate(items)) >= limit:
            break
    return deduplicate(items)[:limit]


def collect_local_tech(directory: str, limit: int = 3) -> list[dict[str, Any]]:
    if not directory or not os.path.isdir(directory):
        return []
    files = sorted(Path(directory).glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        return []
    path = files[0]
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    published = datetime.datetime.fromtimestamp(
        path.stat().st_mtime, tz=datetime.timezone.utc
    ).isoformat()
    matches = re.findall(
        r"### \d+\.\d+\s+([^\n]+)\s*\(\[([^\]]+)\]\((https?://[^\)]+)\)\)",
        content,
    )
    return [
        {
            "name": title.strip(),
            "repo": repo.strip(),
            "url": url.strip(),
            "published": published,
            "source_url": str(path),
        }
        for title, repo, url in matches[:limit]
    ]
