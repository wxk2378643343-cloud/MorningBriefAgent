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
