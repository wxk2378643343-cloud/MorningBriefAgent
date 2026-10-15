"""Loopback-only HTTP API for the future desktop onboarding UI."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core.agent.discovery import discovery_snapshot
from storage.data_sources import list_files, list_sources
from storage.onboarding import complete_step, get_status


class _Handler(BaseHTTPRequestHandler):
    server_version = "MorningBriefLocalAPI/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/v1/onboarding/status":
            self._send_json(get_status(self.server.database_path))
        elif self.path == "/api/v1/providers/discovery":
            self._send_json(discovery_snapshot())
        elif self.path == "/api/v1/data-sources":
            self._send_json({"sources": list_sources(database_path=self.server.database_path)})
        elif self.path.startswith("/api/v1/files"):
            source_id = self._query_value("source_id")
            if not source_id:
                self._send_json({"error": "source_id_required"}, HTTPStatus.BAD_REQUEST)
            else:
                self._send_json({
                    "files": list_files(
                        source_id, database_path=self.server.database_path
                    )
                })
        else:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/v1/onboarding/complete":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json()
            step_key = str(payload.get("step_key", "")).strip()
            detail = payload.get("detail")
            complete_step(
                step_key,
                detail=str(detail) if detail is not None else None,
                database_path=self.server.database_path,
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json(
                {"error": "invalid_request", "message": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return
        self._send_json(get_status(self.server.database_path))

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 64 * 1024:
            raise ValueError("request too large")
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            raise TypeError("JSON object required")
        return payload

    def _query_value(self, name: str) -> str | None:
        from urllib.parse import parse_qs, urlparse

        values = parse_qs(urlparse(self.path).query).get(name, [])
        return values[0] if values else None

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args: object) -> None:
        return


class LocalApplicationServer(ThreadingHTTPServer):
    """A localhost-only server owned by the desktop application."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, database_path: str | Path | None = None, port: int = 0):
        super().__init__(("127.0.0.1", port), _Handler)
        self.database_path = database_path


def create_local_server(
    *,
    database_path: str | Path | None = None,
    port: int = 0,
) -> LocalApplicationServer:
    """Create, but do not start, a loopback-only application API server."""
    return LocalApplicationServer(database_path=database_path, port=port)
