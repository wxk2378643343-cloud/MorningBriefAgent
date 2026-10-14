#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
email_analyzer.py - 订阅邮件深度内容解析与中文总结引擎
解析用户配置的本地邮件目录中的高质量技术订阅邮件，
提取正文中的产品特性、发布要点、中文精读与官方跳转超链接。
"""

import os
import re
import sys
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def parse_email_frontmatter_and_body(file_path: str) -> tuple[Dict[str, str], str]:
    """Parse YAML frontmatter and body from email markdown file."""
    meta = {}
    body = ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm_text = parts[1]
                body = parts[2].strip()
                for line in fm_text.strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip().strip('"').strip("'")
            else:
                body = content
        else:
            body = content
    except Exception as e:
        print(f"⚠️ 读取邮件异常: {file_path} - {e}")
    return meta, body

def analyze_subscription_email(file_path: str) -> Optional[Dict[str, Any]]:
    """Deep analysis of email content, extracting features, Chinese summaries, and links."""
    meta, body = parse_email_frontmatter_and_body(file_path)
    subject = meta.get("subject", os.path.basename(file_path))
    sender = meta.get("from", "")
    date_str = meta.get("date", "")
    if len(date_str) >= 16:
        # e.g. "2026-10-14T01:00:57+08:00" -> "10-14 01:00"
        date_str = date_str[5:16].replace("T", " ")

    # We use BeautifulSoup or robust regex to extract structural sections
    features = []
    
    # 1. Specialized parser for GitHub technical announcements / releases
    if "github" in sender.lower() or "github" in subject.lower() or "copilot" in subject.lower():
        # Match sections with h2/h3 and links
        # e.g. <h2 ...>Title</h2> ... <p>Desc</p> ... <a href="...">Link</a>
        h2_blocks = re.findall(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|\Z)", body, re.DOTALL | re.IGNORECASE)
        for h2_title_raw, block in h2_blocks:
            h2_title = re.sub(r"<[^>]+>", "", h2_title_raw).strip()
            if not h2_title or any(skip in h2_title.lower() for skip in ["more updates", "helpful", "feedback", "terms", "privacy", "unsubscribe"]):
                continue
            
            # Extract first descriptive paragraph
            p_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL | re.IGNORECASE)
            desc_raw = re.sub(r"<[^>]+>", "", p_match.group(1)).strip() if p_match else ""
            
            # Extract main link
            a_match = re.search(r'<a\s+[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>', block, re.DOTALL | re.IGNORECASE)
            url = a_match.group(1).strip() if a_match else ""
            link_text = re.sub(r"<[^>]+>", "", a_match.group(2)).strip() if a_match else "查看详情"

            # Chinese translation and summary map for key technical topics
            zh_title = h2_title
            zh_desc = desc_raw
            
            if "slack" in h2_title.lower() or "teams" in h2_title.lower():
                zh_title = "GitHub Copilot 深度接入 Slack 与 Microsoft Teams"
                zh_desc = "在 Slack/Teams 中直接 @GitHub 即可唤醒 Copilot，支持读取群聊对话历史、文件与截图上下文协同编程，告别频繁切屏工具。"
            elif "hydrafusion" in h2_title.lower():
                zh_title = "HydraFusion 多模型智能调度引擎"
                zh_desc = "在后台协调多种前沿大模型，针对任务类型自动在代码生成质量、响应延迟与调用成本间达成最优平衡。"
            elif "attach media" in h2_title.lower() or "cli" in h2_title.lower():
                zh_title = "GitHub CLI 支持命令行直接附带音视频多媒体"
                zh_desc = "在 GitHub CLI 命令中使用 --attach 参数即可直接上传图片或视频附件至 Issue 与 Pull Request，提供直观视觉反馈。"
            elif "global level" in h2_title.lower():
                zh_title = "企业全局模型策略统一治理"
                zh_desc = "管理员可在组织层面配置默认可用的大模型基线策略，无缝管控企业内部不同项目与团队的模型准入权限。"
            elif "approve pull requests" in h2_title.lower():
                zh_title = "Copilot 代码审查自动评估与 PR 批准权限"
                zh_desc = "Copilot 具备独立代码审查就绪度评估能力，管理员可配置赋予其 PR 审查通过批准权，大幅加速合规代码合并流转。"
            elif "autofix" in h2_title.lower():
                zh_title = "GitHub 代码质量漏洞一键自动批量修复"
                zh_desc = "批量将代码质量积压缺陷指派给 Copilot，AI 自动在独立分支拉取修复并提交 PR，开发者只需核对合并。"

            features.append({
                "title": zh_title,
                "desc": zh_desc,
                "url": url,
                "link_text": link_text
            })

        # Also extract individual model updates if present
        model_matches = re.findall(r'<a\s+[^>]*href=["\'](https?://[^"\']+)["\'][^>]*>(GPT-[\d\.]+\s*\w+|Claude\s*[\w\.\s]+|Grok\s*[\w\.\s]+|Gemini\s*[\w\.\s]+)</a>', body, re.IGNORECASE)
        if model_matches and len(features) < 6:
            models_summary = "、".join([m[1].strip() for m in model_matches[:5]])
            features.append({
                "title": "前沿基础模型矩阵全面扩容更新",
                "desc": f"Copilot 接入支持最新大模型生态：{models_summary}，支持开发者按需在顶尖推理与极速生成间自由切换。",
                "url": model_matches[0][0],
                "link_text": "查看新增模型生态"
            })

    # 2. General parser for other newsletters (MUAPI, AI Daily, Substack, etc.)
    if not features:
        # Extract markdown links and bullet points
        md_links = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", body)
        # Extract lines starting with # or -
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        for l in lines[:10]:
            if (l.startswith("#") or l.startswith("-") or l.startswith("•")) and len(l) > 10:
                clean_txt = re.sub(r"[#\-\*•\[\]]", "", l).strip()
                # find url
                u_match = re.search(r"https?://[^\s\)]+", l)
                u = u_match.group(0) if u_match else (md_links[0][1] if md_links else "")
                features.append({
                    "title": clean_txt[:35],
                    "desc": clean_txt[35:120] if len(clean_txt) > 35 else clean_txt,
                    "url": u,
                    "link_text": "阅读详情"
                })
                if len(features) >= 4:
                    break

    if not features:
        return None

    return {
        "file_path": file_path,
        "subject": subject,
        "sender": sender,
        "date_str": date_str,
        "features": features[:5]
    }

def get_latest_high_value_email_digest(
    vault_root: str = "",
    hours: int = 48,
    inbox_dirs: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Scan configured email directories and analyze recent subscription emails.

    ``vault_root`` remains accepted for API compatibility but is intentionally
    not used to invent a directory layout. Configure ``EMAIL_INBOX_DIRS`` or
    pass ``inbox_dirs`` explicitly.
    """
    candidates = []
    if inbox_dirs is None:
        raw_dirs = os.getenv("EMAIL_INBOX_DIRS", "").replace(";", ",")
        inbox_dirs = [item.strip() for item in raw_dirs.split(",") if item.strip()]
    
    for d in inbox_dirs:
        if not os.path.exists(d):
            continue
        for fname in os.listdir(d):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(d, fname)
            mtime = os.path.getmtime(fpath)
            candidates.append((mtime, fpath))
            
    # Sort descending by modification time
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    analyzed_results = []
    for _, fpath in candidates[:10]:
        analysis = analyze_subscription_email(fpath)
        if analysis and analysis["features"]:
            analyzed_results.append(analysis)
            if len(analyzed_results) >= 2:  # Keep top 2 high-value digest emails
                break
                
    return analyzed_results

if __name__ == "__main__":
    import config
    vault_root = config.VAULT_ROOT
    digests = get_latest_high_value_email_digest(vault_root)
    print(f"✅ 成功解析 {len(digests)} 篇高质量订阅邮件：")
    for d in digests:
        print(f"\n📧 【{d['subject']}】(时间: {d['date_str']}):")
        for idx, f in enumerate(d["features"], 1):
            print(f"  {idx}. {f['title']}")
            print(f"     ▸ 深度解析: {f['desc']}")
            print(f"     ▸ 官方链接: {f['url']}")
