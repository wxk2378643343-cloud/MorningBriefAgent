#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Personal portfolio snapshot and market context.

Private holdings are loaded from ``data/portfolio.json`` (or PORTFOLIO_FILE).
The module reports configured facts and market estimates; it does not generate
buy/sell orders or claim to provide regulated investment advice.
"""

import datetime
import json
import logging
import os
import sys
import urllib.request
from typing import Any, Dict, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

for proxy_var in (
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"
):
    os.environ.pop(proxy_var, None)
os.environ["NO_PROXY"] = "feishu.cn,open.feishu.cn,sinajs.cn,sina.com.cn,127.0.0.1,localhost"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FundDailyAdvisor")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.runtime import config
from core.integrations.feishu.gateway import feishu_gateway
from core.integrations.feishu.idempotency import make_key
from storage.market import save_fund_snapshot

BENCHMARK_SYMBOLS = ["sh000001", "sz399006", "hkHSI"]


def load_portfolio_config(path: str | None = None) -> Dict[str, Any]:
    """Load private portfolio data from an ignored JSON file."""
    target = path or config.PORTFOLIO_FILE
    if not target or not os.path.isfile(target):
        return {"portfolio": [], "watchlist": []}
    try:
        with open(target, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("portfolio config must be a JSON object")
        data.setdefault("portfolio", [])
        data.setdefault("watchlist", [])
        return data
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.error("读取私人持仓配置失败: %s", exc)
        return {"portfolio": [], "watchlist": []}


def _symbols(config_data: Dict[str, Any]) -> List[str]:
    symbols = list(BENCHMARK_SYMBOLS)
    for section in ("portfolio", "watchlist"):
        for item in config_data.get(section, []):
            symbol = item.get("proxy_symbol")
            if symbol:
                symbols.append(symbol)
    return sorted(set(symbols))


def fetch_realtime_quotes(symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """Fetch index/ETF snapshots used only as rough reference values."""
    if not symbols:
        return {}
    url = f"{config.MARKET_DATA_URL.rstrip('/')}/list={','.join(symbols)}"
    request = urllib.request.Request(
        url,
        headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"},
    )
    quotes: Dict[str, Dict[str, float]] = {}
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            content = response.read().decode("gbk", errors="ignore")
        for line in content.splitlines():
            if "=\"" not in line or "str_" not in line:
                continue
            symbol = line.split("str_", 1)[1].split("=", 1)[0]
            parts = line.split("=\"", 1)[1].split(",")
            try:
                if symbol == "hkHSI" and len(parts) > 8:
                    quotes[symbol] = {
                        "price": float(parts[6] or parts[2] or 0),
                        "change_pct": float(parts[8] or 0),
                    }
                elif symbol.startswith("gb_") and len(parts) > 4:
                    price = float(parts[1] or 0)
                    change_pct = float(parts[2] or 0)
                    quotes[symbol] = {"price": price, "change_pct": change_pct}
                elif len(parts) > 3:
                    previous = float(parts[2] or 0)
                    price = float(parts[3] or previous)
                    change = ((price - previous) / previous * 100) if previous else 0.0
                    quotes[symbol] = {"price": price, "change_pct": change}
            except (ValueError, IndexError):
                continue
    except Exception as exc:
        logger.error("获取行情快照失败: %s", exc)
    return quotes


def persist_quote_snapshots(
    quotes: Dict[str, Dict[str, float]],
    *,
    observed_at: datetime.datetime | None = None,
) -> None:
    """Persist market observations with source time; never overwrite history."""
    observed_at = observed_at or datetime.datetime.now(datetime.timezone.utc)
    for symbol, quote in quotes.items():
        try:
            save_fund_snapshot(
                fund_code=symbol,
                price=quote.get("price"),
                change_percent=quote.get("change_pct"),
                market_time=observed_at.isoformat(timespec="seconds"),
                data_source=config.MARKET_DATA_URL,
                is_realtime=True,
            )
        except Exception as exc:
            logger.warning("保存行情快照失败 symbol=%s error=%s", symbol, exc)


def _trading_days_until(target_date: str) -> int:
    try:
        end = datetime.datetime.strptime(target_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return 0
    today = datetime.date.today()
    if end < today:
        return 0
    return sum(
        1
        for offset in range((end - today).days + 1)
        if (today + datetime.timedelta(days=offset)).weekday() < 5
    )


def generate_advisor_report() -> str:
    """Create a factual snapshot from the user's local portfolio configuration."""
    config_data = load_portfolio_config()
    portfolio = config_data.get("portfolio", [])
    watchlist = config_data.get("watchlist", [])
    if not portfolio:
        return (
            "⚠️ **未配置私人持仓数据**\n\n"
            "复制 `data/portfolio.example.json` 为 `data/portfolio.json`，"
            "填写本地数据后重试。该文件已被 Git 忽略。"
        )

    quotes = fetch_realtime_quotes(_symbols(config_data))
    persist_quote_snapshots(quotes)
    total_cost = sum(float(item.get("cost_value", 0)) for item in portfolio)
    total_value = sum(float(item.get("current_value", 0)) for item in portfolio)
    total_profit = sum(float(item.get("profit", 0)) for item in portfolio)
    total_rate = total_profit / total_cost * 100 if total_cost else 0.0
    today_estimate = 0.0

    rows = []
    for item in portfolio:
        quote = quotes.get(item.get("proxy_symbol", ""), {})
        change = float(quote.get("change_pct", 0))
        value = float(item.get("current_value", 0))
        estimate = value * change / 100
        today_estimate += estimate
        rows.append((item, change, estimate))

    lines = [
        f"⏱️ **生成时间**：`{datetime.datetime.now():%Y-%m-%d %H:%M}`",
        "",
        "💰 **本地配置汇总**：",
        f"• 投入本金：`¥{total_cost:.2f}`",
        f"• 当前市值：`¥{total_value:.2f}`",
        f"• 配置内累计盈亏：`¥{total_profit:+.2f}` (`{total_rate:+.2f}%`)",
        f"• 代理标的推算今日波动：`¥{today_estimate:+.2f}`",
        "",
    ]

    target = float(config_data.get("profit_target", 0) or 0)
    target_date = config_data.get("target_date", "")
    if target or target_date:
        days = _trading_days_until(target_date)
        lines.extend([
            "🎯 **自定义记录目标**：",
            f"• 目标日期：`{target_date or '未设置'}`",
            f"• 目标收益：`¥{target:.2f}`",
            f"• 粗略剩余工作日：`{days}`（未扣除法定休市日）",
            "",
        ])

    lines.extend(["📋 **持仓快照**："])
    for index, (item, change, estimate) in enumerate(rows, 1):
        lines.extend([
            f"**{index}. {item.get('name', '未命名标的')}** (`{item.get('code', '-')}`)",
            (
                f"• 分类：{item.get('category', '-')} | 市值：`¥{float(item.get('current_value', 0)):.2f}` "
                f"| 累计：`¥{float(item.get('profit', 0)):+.2f}`"
            ),
            (
                f"• 代理标的：{item.get('proxy_name', item.get('proxy_symbol', '-'))} "
                f"`{change:+.2f}%` | 粗略影响：`¥{estimate:+.2f}`"
            ),
            f"• 自定义备注：{item.get('strategy', '无')}",
        ])

    if watchlist:
        lines.extend(["", "🌟 **本地观察列表**："])
        for item in watchlist:
            lines.append(
                f"• {item.get('name', '未命名标的')} (`{item.get('code', '-')}`)："
                f"{item.get('plan_note', '无备注')}"
            )

    lines.extend([
        "",
        "> 本报告只汇总本地配置与公开行情代理值，可能延迟或失真；不构成投资建议或交易指令。",
    ])
    return "\n".join(lines)


def send_daily_advisor_card() -> None:
    """Generate and send the snapshot through the configured Feishu client."""
    logger.info("启动个人持仓与市场摘要...")
    content = generate_advisor_report()
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"📈 个人持仓与市场摘要 ({datetime.date.today():%Y-%m-%d})",
            },
            "template": "turquoise",
        },
        "elements": [{"tag": "markdown", "content": content}],
    }
    if not feishu_gateway.send_card_once(
        card, make_key("feishu-card", "fund", datetime.date.today().isoformat())
    ):
        logger.warning("飞书卡片推送未确认成功，请检查配置与日志")


main = send_daily_advisor_card

if __name__ == "__main__":
    main()
