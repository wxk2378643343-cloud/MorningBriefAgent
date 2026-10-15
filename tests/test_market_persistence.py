"""Tests for persisted market observations."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.finance import fund_advisor
from storage.sqlite import connect


class MarketPersistenceTests(unittest.TestCase):
    def test_portfolio_positions_are_idempotent_per_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "market.sqlite3"
            observed_at = datetime.datetime(
                2026, 10, 15, 8, tzinfo=datetime.timezone.utc
            )
            with mock.patch.object(
                fund_advisor.config,
                "SQLITE_DATABASE_PATH",
                str(database),
            ), mock.patch.object(
                fund_advisor.config,
                "PORTFOLIO_FILE",
                "D:/private/portfolio.json",
            ):
                portfolio = [{
                    "code": "000001",
                    "name": "示例基金",
                    "shares": 100,
                    "cost_price": 1.25,
                }]
                fund_advisor.persist_portfolio_positions(
                    portfolio, recorded_at=observed_at
                )
                fund_advisor.persist_portfolio_positions(
                    portfolio, recorded_at=observed_at.replace(hour=18)
                )

            connection = connect(database)
            try:
                rows = connection.execute(
                    "SELECT fund_code, shares, cost_price FROM fund_records"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(dict(rows[0]), {
            "fund_code": "000001",
            "shares": 100.0,
            "cost_price": 1.25,
        })

    def test_quote_snapshots_keep_each_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "market.sqlite3"
            with mock.patch.object(
                fund_advisor.config,
                "SQLITE_DATABASE_PATH",
                str(database),
            ):
                fund_advisor.persist_quote_snapshots(
                    {"sh000001": {"price": 3200, "change_pct": 0.5}},
                    observed_at=datetime.datetime(
                        2026, 10, 15, tzinfo=datetime.timezone.utc
                    ),
                )
            connection = connect(database)
            try:
                row = connection.execute(
                    "SELECT fund_code, price, is_realtime FROM fund_market_snapshots"
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(dict(row), {
            "fund_code": "sh000001",
            "price": 3200.0,
            "is_realtime": 1,
        })
