"""Loopback-only HTTP API for the future desktop onboarding UI."""

from __future__ import annotations

import json
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core.agent.discovery import discovery_snapshot
from storage.credentials import get_secret, set_secret
from storage.data_sources import (
    inspect_sqlite,
    list_files,
    list_sources,
    read_file_binary,
    read_file_preview,
    write_file_text,
    delete_file,
    register_source,
    scan_source,
)
from storage.onboarding import complete_step, get_status, reset_all, skip_step
from storage.workspace import default_workspace_root, initialize_workspace, save_personal_context, workspace_info
from storage.agent_status import read_agent_status
from core.runtime.config import PROJECT_ROOT
from storage.database_browser import create as create_record, delete as delete_record, rows as database_rows, tables as database_tables, update as update_record
from storage.workflows import list_runs, list_workflows, run_workflow


class _Handler(BaseHTTPRequestHandler):
    server_version = "MorningBriefLocalAPI/1.0"

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

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
        elif self.path == "/api/v1/agent/status":
            self._send_json(read_agent_status(self.server.database_path))
        elif self.path == "/api/v1/workflows":
            self._send_json({"workflows": list_workflows(), "runs": list_runs(self.server.database_path)})
        elif self.path == "/api/v1/database/tables":
            self._send_json({"tables": database_tables(self.server.database_path)})
        elif self.path.startswith("/api/v1/database/table"):
            table = self._query_value("table")
            if not table:
                self._send_json({"error": "table_required"}, HTTPStatus.BAD_REQUEST)
            else:
                try:
                    self._send_json(database_rows(self.server.database_path, table))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        elif self.path == "/api/v1/data-sources":
            sources = list_sources(database_path=self.server.database_path)
            if not sources:
                demo_root = PROJECT_ROOT / "demo" / "obsidian"
                if demo_root.is_dir():
                    source_id = register_source("Demo Obsidian", demo_root, database_path=self.server.database_path)
                    scan_source(source_id, database_path=self.server.database_path)
                    sources = list_sources(database_path=self.server.database_path)
            self._send_json({"sources": sources})
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
        if self.path == "/api/v1/onboarding/reset":
            self._send_json(reset_all(database_path=self.server.database_path))
            return
        if self.path in {"/api/v1/workspace/select", "/api/v1/workspace/initialize"}:
            try:
                payload = self._read_json()
                root_path = str(payload.get("root_path", "")).strip() or str(default_workspace_root())
                result = initialize_workspace(root_path, database_path=self.server.database_path)
                source_id = register_source(
                    "Obsidian 知识库",
                    result["vault_path"],
                    database_path=self.server.database_path,
                )
                result["source_id"] = source_id
                result["indexed_files"] = scan_source(
                    source_id,
                    database_path=self.server.database_path,
                )
                self._send_json(result)
            except (ValueError, TypeError, OSError) as exc:
                self._send_json({"error": "workspace_initialization_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/v1/workspace/initialize-demo":
            try:
                demo_root = PROJECT_ROOT / "demo" / "obsidian"
                initialize_workspace(PROJECT_ROOT / "demo", database_path=self.server.database_path)
                source_id = register_source("Demo Obsidian", demo_root, database_path=self.server.database_path)
                indexed = scan_source(source_id, database_path=self.server.database_path)
                self._send_json({"workspace": workspace_info(self.server.database_path), "source_id": source_id, "indexed_files": indexed})
            except (ValueError, OSError, TypeError) as exc:
                self._send_json({"error": "demo_initialization_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/v1/workspace/scan":
            self._send_json({"workspace": workspace_info(self.server.database_path)})
            return
        if self.path.startswith("/api/v1/providers/") and self.path.endswith("/credentials"):
            provider = self.path.split("/")[4]
            try:
                payload = self._read_json()
                secret = str(payload.get("api_key", "")).strip()
                if not secret:
                    raise ValueError("api_key_required")
                set_secret(f"provider:{provider}:api_key", secret)
                self._send_json({"provider": provider, "configured": True})
            except (ValueError, RuntimeError, TypeError) as exc:
                self._send_json({"error": "credential_save_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/v1/providers/") and self.path.endswith("/test"):
            provider = self.path.split("/")[4]
            configured = bool(get_secret(f"provider:{provider}:api_key"))
            self._send_json(
                {"provider": provider, "ok": configured, "message": "凭据已保存" if configured else "未配置 API Key"},
                HTTPStatus.OK if configured else HTTPStatus.BAD_REQUEST,
            )
            return
        if self.path.startswith("/api/v1/channels/") and self.path.endswith("/credentials"):
            channel = self.path.split("/")[4]
            try:
                payload = self._read_json()
                for key in ("app_id", "app_secret", "user_open_id", "chat_id"):
                    value = str(payload.get(key, "")).strip()
                    if not value:
                        raise ValueError(f"{key}_required")
                    set_secret(f"channel:{channel}:{key}", value)
                self._send_json({"channel": channel, "configured": True})
            except (ValueError, RuntimeError, TypeError) as exc:
                self._send_json({"error": "credential_save_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/v1/channels/") and self.path.endswith("/test"):
            channel = self.path.split("/")[4]
            configured = bool(get_secret(f"channel:{channel}:app_id") and get_secret(f"channel:{channel}:app_secret"))
            self._send_json(
                {"channel": channel, "ok": configured, "message": "凭据已保存" if configured else "未配置飞书 App ID 或 Secret"},
                HTTPStatus.OK if configured else HTTPStatus.BAD_REQUEST,
            )
            return
        if self.path == "/api/v1/profile":
            try:
                self._send_json(save_personal_context(self._read_json(), database_path=self.server.database_path))
            except (ValueError, OSError, TypeError) as exc:
                self._send_json({"error": "profile_save_failed", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/v1/files":
            try:
                payload = self._read_json()
                result = write_file_text(
                    str(payload.get("source_id", "")),
                    str(payload.get("path", "")),
                    str(payload.get("content", "")),
                    database_path=self.server.database_path,
                )
                self._send_json({"file": result})
            except (KeyError, ValueError, FileNotFoundError, OSError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path.startswith("/api/v1/workflows/") and self.path.endswith("/run"):
            key = self.path.split("/")[4]
            try:
                self._send_json(run_workflow(key, self.server.database_path), HTTPStatus.ACCEPTED)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if self.path == "/api/v1/database/records":
            try:
                payload = self._read_json()
                result = create_record(self.server.database_path, payload["table"], payload["record"])
                self._send_json({"record": result}, HTTPStatus.CREATED)
            except (KeyError, ValueError, sqlite3.DatabaseError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
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
            operation = skip_step if payload.get("skipped") else complete_step
            operation(
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

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path not in {"/api/v1/files", "/api/v1/database/records"}:
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json()
            if self.path == "/api/v1/files":
                delete_file(
                    str(payload.get("source_id", "")),
                    str(payload.get("path", "")),
                    database_path=self.server.database_path,
                )
            else:
                delete_record(self.server.database_path, payload["table"], payload["id"])
            self._send_json({"deleted": True})
        except (KeyError, ValueError, FileNotFoundError, OSError, sqlite3.DatabaseError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_PATCH(self) -> None:  # noqa: N802
        if self.path != "/api/v1/database/records":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json()
            result = update_record(self.server.database_path, payload["table"], payload["id"], payload["record"])
            self._send_json({"record": result})
        except (KeyError, ValueError, sqlite3.DatabaseError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

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
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(encoded)

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in {"http://127.0.0.1:4173", "http://localhost:4173"}:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

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
