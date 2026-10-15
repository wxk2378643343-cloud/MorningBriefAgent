"""Loopback-only HTTP API for the future desktop onboarding UI."""

from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core.agent.discovery import discovery_snapshot
from storage.credentials import set_secret
from storage.data_sources import (
    inspect_sqlite,
    list_files,
    list_sources,
    read_file_binary,
    read_file_preview,
    register_source,
    scan_source,
)
from storage.onboarding import complete_step, get_status
from storage.workspace import initialize_workspace, save_personal_context, workspace_info


class _Handler(BaseHTTPRequestHandler):
    server_version = "MorningBriefLocalAPI/1.0"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/v1/health":
            self._send_json({"status": "ok", "service": "morningbrief-local-api"})
        elif self.path == "/api/v1/app/status":
            self._send_json({"service": "ready", "workspace": workspace_info(self.server.database_path)})
        elif self.path == "/api/v1/workspace":
            self._send_json(workspace_info(self.server.database_path))
        elif self.path == "/api/v1/onboarding/status":
            self._send_json(get_status(self.server.database_path))
        elif self.path == "/api/v1/providers/discovery":
            self._send_json(discovery_snapshot())
        elif self.path == "/api/v1/providers":
            self._send_json(discovery_snapshot())
        elif self.path == "/api/v1/channels":
            self._send_json({"channels": discovery_snapshot()["channels"]})
        elif self.path == "/api/v1/data-sources":
            self._send_json({"sources": list_sources(database_path=self.server.database_path)})
        elif self.path.startswith("/api/v1/file-binary"):
            source_id = self._query_value("source_id")
            relative_path = self._query_value("path")
            if not source_id or not relative_path:
                self._send_json({"error": "source_id_and_path_required"}, HTTPStatus.BAD_REQUEST)
            else:
                try:
                    self._send_json({"file": read_file_binary(source_id, relative_path, database_path=self.server.database_path)})
                except (KeyError, FileNotFoundError):
                    self._send_json({"error": "file_not_found"}, HTTPStatus.NOT_FOUND)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        elif self.path.startswith("/api/v1/files"):
            source_id = self._query_value("source_id")
            relative_path = self._query_value("path")
            if not source_id:
                self._send_json({"error": "source_id_required"}, HTTPStatus.BAD_REQUEST)
            elif relative_path:
                try:
                    self._send_json({
                        "file": read_file_preview(
                            source_id,
                            relative_path,
                            database_path=self.server.database_path,
                        )
                    })
                except (KeyError, FileNotFoundError):
                    self._send_json({"error": "file_not_found"}, HTTPStatus.NOT_FOUND)
                except ValueError as exc:
                    self._send_json(
                        {"error": str(exc)}, HTTPStatus.BAD_REQUEST
                    )
            else:
                self._send_json({
                    "files": list_files(
                        source_id, database_path=self.server.database_path
                    )
                })
        elif self.path.startswith("/api/v1/sqlite"):
            source_id = self._query_value("source_id")
            relative_path = self._query_value("path")
            table = self._query_value("table")
            if not source_id or not relative_path:
                self._send_json(
                    {"error": "source_id_and_path_required"},
                    HTTPStatus.BAD_REQUEST,
                )
            else:
                try:
                    self._send_json({
                        "database": inspect_sqlite(
                            source_id,
                            relative_path,
                            table=table,
                            database_path=self.server.database_path,
                        )
                    })
                except (KeyError, FileNotFoundError):
                    self._send_json({"error": "database_not_found"}, HTTPStatus.NOT_FOUND)
                except (ValueError, sqlite3.DatabaseError) as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        else:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path in {"/api/v1/workspace/select", "/api/v1/workspace/initialize"}:
            try:
                payload = self._read_json()
                root_path = str(payload.get("root_path", "")).strip()
                if not root_path:
                    raise ValueError("root_path_required")
                result = initialize_workspace(root_path, database_path=self.server.database_path)
                self._send_json(result)
            except (ValueError, TypeError, OSError) as exc:
                self._send_json({"error": "workspace_initialization_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/v1/workspace/scan":
            self._send_json({"workspace": workspace_info(self.server.database_path)})
            return
        if self.path.startswith("/api/v1/providers/") and self.path.endswith("/credentials"):
            provider = self.path.split("/")[4]
            try:
                payload = self._read_json()
                secret = str(payload.get("api_key", "")).strip()
                set_secret(f"provider:{provider}:api_key", secret)
                self._send_json({"provider": provider, "configured": True})
            except (ValueError, RuntimeError, TypeError) as exc:
                self._send_json({"error": "credential_save_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/v1/channels/") and self.path.endswith("/credentials"):
            channel = self.path.split("/")[4]
            try:
                payload = self._read_json()
                for key in ("app_id", "app_secret", "user_open_id", "chat_id"):
                    value = str(payload.get(key, "")).strip()
                    if value:
                        set_secret(f"channel:{channel}:{key}", value)
                self._send_json({"channel": channel, "configured": True})
            except (ValueError, RuntimeError, TypeError) as exc:
                self._send_json({"error": "credential_save_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/v1/profile":
            try:
                self._send_json(save_personal_context(self._read_json(), database_path=self.server.database_path))
            except (ValueError, OSError, TypeError) as exc:
                self._send_json({"error": "profile_save_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/v1/data-sources":
            try:
                payload = self._read_json()
                root_path = str(payload.get("root_path", "")).strip()
                name = str(payload.get("name", "")).strip()
                if not root_path:
                    raise ValueError("root_path_required")
                source_id = register_source(
                    name or Path(root_path).name,
                    root_path,
                    database_path=self.server.database_path,
                )
                indexed = scan_source(
                    source_id,
                    database_path=self.server.database_path,
                )
            except (ValueError, TypeError, OSError) as exc:
                self._send_json(
                    {"error": "invalid_data_source", "message": str(exc)},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            self._send_json(
                {"source_id": source_id, "indexed_files": indexed}
            )
            return
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
