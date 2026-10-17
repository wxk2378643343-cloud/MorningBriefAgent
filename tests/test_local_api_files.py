import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from unittest.mock import patch

from core.application.local_api import create_local_server
from storage.data_sources import hash_file, register_source, scan_source
from storage.sqlite import connect, initialize


class LocalFileApiTests(unittest.TestCase):
    def test_health_endpoint_is_local_service_probe(self):
        with patch(
            "core.application.local_api.reconcile_pending_file_operations"
        ) as reconcile:
            server = create_local_server()
        reconcile.assert_called_once_with(database_path=None)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = self._get(
                f"http://127.0.0.1:{server.server_port}/api/v1/health"
            )
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["service"], "morningbrief-local-api")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_sources_and_files_are_readable_as_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            (root / "brief.md").write_text("# Brief", encoding="utf-8")
            (root / "pixel.png").write_bytes(
                bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489")
            )
            sqlite_file = root / "sample.sqlite3"
            import sqlite3
            database_handle = sqlite3.connect(sqlite_file)
            try:
                database_handle.execute("CREATE TABLE notes (id INTEGER, body TEXT)")
                database_handle.execute("INSERT INTO notes VALUES (1, 'hello')")
                database_handle.commit()
            finally:
                database_handle.close()
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            source_id = register_source("Vault", root, database_path=database)
            scan_source(source_id, database_path=database)

            server, thread, base = self._start_server(database)
            try:
                sources = self._get(f"{base}/api/v1/data-sources")
                files = self._get(
                    f"{base}/api/v1/files?source_id={source_id}&sort=recent"
                )
                preview = self._get(
                    f"{base}/api/v1/files?source_id={source_id}&path=brief.md"
                )
                database = self._get(
                    f"{base}/api/v1/sqlite?source_id={source_id}"
                    f"&path=sample.sqlite3&table=notes"
                )
                binary = self._get(
                    f"{base}/api/v1/file-binary?source_id={source_id}&path=pixel.png"
                )
                files_by_path = {
                    item["relative_path"]: item for item in files["files"]
                }
                self.assertEqual(sources["sources"][0]["name"], "Vault")
                self.assertEqual(files["sort"], "recent")
                self.assertEqual(
                    files_by_path["brief.md"]["source"]["name"],
                    "Vault",
                )
                self.assertEqual(
                    files_by_path["brief.md"]["sync_status"],
                    "synced",
                )
                self.assertTrue(
                    files_by_path["brief.md"]["updated_at"].endswith("Z")
                )
                self.assertEqual(preview["file"]["content"], "# Brief")
                self.assertEqual(database["database"]["tables"], ["notes"])
                self.assertEqual(database["database"]["rows"][0]["body"], "hello")
                self.assertEqual(binary["file"]["content_type"], "image/png")
                created = self._post(
                    f"{base}/api/v1/data-sources",
                    {"name": "Vault copy", "root_path": str(root)},
                )
                self.assertEqual(created["indexed_files"], 3)
                moved = self._patch(
                    f"{base}/api/v1/files",
                    {
                        "source_id": source_id,
                        "path": "brief.md",
                        "destination_path": "archive/renamed.md",
                    },
                )
                self.assertEqual(moved["destination_path"], "archive/renamed.md")
                self.assertFalse((root / "brief.md").exists())
                self.assertTrue((root / "archive" / "renamed.md").is_file())
                self.assertEqual(
                    "# Brief",
                    (root / "archive" / "renamed.md").read_text(encoding="utf-8"),
                )
            finally:
                self._stop_server(server, thread)

    def test_read_search_save_delete_restore_duplicate_and_restart_matrix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, database, source_id = self._workspace(temp_dir)
            note = root / "notes" / "today.md"
            note.parent.mkdir()
            note.write_text("# Today\n\nneedle in content", encoding="utf-8")
            scan_source(source_id, database_path=database)

            server, thread, base = self._start_server(database)
            try:
                preview = self._get(
                    f"{base}/api/v1/files?"
                    + urlencode({"source_id": source_id, "path": "notes/today.md"})
                )
                self.assertEqual(
                    preview["file"]["content"], "# Today\n\nneedle in content"
                )
                search = self._get(
                    f"{base}/api/v1/files?"
                    + urlencode({"source_id": source_id, "query": "needle"})
                )
                self.assertEqual(
                    [item["relative_path"] for item in search["files"]],
                    ["notes/today.md"],
                )
                self.assertEqual(search["files"][0]["match_type"], "content")

                saved = self._post(
                    f"{base}/api/v1/files",
                    {
                        "source_id": source_id,
                        "path": "notes/today.md",
                        "content": "# Updated",
                    },
                )
                self.assertEqual(saved["file"]["content"], "# Updated")

                deletion = self._delete(
                    f"{base}/api/v1/files",
                    {
                        "source_id": source_id,
                        "path": "notes/today.md",
                        "request_id": "delete-today-once",
                    },
                )
                operation_id = deletion["recovery"]["id"]
                self.assertFalse(note.exists())
                self.assertEqual(deletion["recovery"]["status"], "deleted")
                self.assertTrue(
                    (root / deletion["recovery"]["recovery_path"]).is_file()
                )

                duplicate = self._delete(
                    f"{base}/api/v1/files",
                    {
                        "source_id": source_id,
                        "path": "notes/today.md",
                        "request_id": "delete-today-once",
                    },
                )
                self.assertEqual(duplicate["recovery"]["id"], operation_id)
                with connect(database) as connection:
                    operation_count = connection.execute(
                        "SELECT COUNT(*) FROM file_recovery_operations"
                    ).fetchone()[0]
                self.assertEqual(operation_count, 1)
            finally:
                self._stop_server(server, thread)

            server, thread, base = self._start_server(database)
            try:
                files = self._get(
                    f"{base}/api/v1/files?"
                    + urlencode({"source_id": source_id})
                )
                self.assertEqual(files["files"], [])
                recoveries = self._get(
                    f"{base}/api/v1/file-recoveries?"
                    + urlencode({"source_id": source_id})
                )
                self.assertEqual(recoveries["recoveries"][0]["id"], operation_id)

                restored = self._post(
                    f"{base}/api/v1/files/restore",
                    {"source_id": source_id, "operation_id": operation_id},
                )
                self.assertEqual(restored["recovery"]["status"], "restored")
                self.assertEqual(note.read_text(encoding="utf-8"), "# Updated")
                duplicate_restore = self._post(
                    f"{base}/api/v1/files/restore",
                    {"source_id": source_id, "operation_id": operation_id},
                )
                self.assertEqual(
                    duplicate_restore["recovery"]["status"], "restored"
                )
            finally:
                self._stop_server(server, thread)

            server, thread, base = self._start_server(database)
            try:
                preview = self._get(
                    f"{base}/api/v1/files?"
                    + urlencode({"source_id": source_id, "path": "notes/today.md"})
                )
                self.assertEqual(preview["file"]["content"], "# Updated")
            finally:
                self._stop_server(server, thread)

    def test_restore_conflict_never_overwrites_replacement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, database, source_id = self._workspace(temp_dir)
            note = root / "conflict.md"
            note.write_text("original", encoding="utf-8")
            scan_source(source_id, database_path=database)
            server, thread, base = self._start_server(database)
            try:
                deletion = self._delete(
                    f"{base}/api/v1/files",
                    {
                        "source_id": source_id,
                        "path": "conflict.md",
                        "request_id": "conflict-delete",
                    },
                )
                note.write_text("replacement", encoding="utf-8")
                error_status, error_payload = self._error(
                    f"{base}/api/v1/files/restore",
                    {
                        "source_id": source_id,
                        "operation_id": deletion["recovery"]["id"],
                    },
                    method="POST",
                )
                self.assertEqual(error_status, 409)
                self.assertEqual(error_payload["error"], "restore_target_exists")
                self.assertEqual(note.read_text(encoding="utf-8"), "replacement")
            finally:
                self._stop_server(server, thread)

    def test_missing_traversal_and_idempotency_conflicts_are_bounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, database, source_id = self._workspace(temp_dir)
            (root / "first.md").write_text("first", encoding="utf-8")
            (root / "second.md").write_text("second", encoding="utf-8")
            outside = Path(temp_dir) / "outside.md"
            outside.write_text("private", encoding="utf-8")
            scan_source(source_id, database_path=database)
            server, thread, base = self._start_server(database)
            try:
                missing_status, _ = self._error(
                    f"{base}/api/v1/files",
                    {"source_id": source_id, "path": "missing.md"},
                    method="DELETE",
                )
                self.assertEqual(missing_status, 404)

                traversal_status, _ = self._error(
                    f"{base}/api/v1/files",
                    {"source_id": source_id, "path": "../outside.md"},
                    method="DELETE",
                )
                self.assertEqual(traversal_status, 400)
                self.assertEqual(outside.read_text(encoding="utf-8"), "private")

                self._delete(
                    f"{base}/api/v1/files",
                    {
                        "source_id": source_id,
                        "path": "first.md",
                        "request_id": "same-request",
                    },
                )
                conflict_status, _ = self._error(
                    f"{base}/api/v1/files",
                    {
                        "source_id": source_id,
                        "path": "second.md",
                        "request_id": "same-request",
                    },
                    method="DELETE",
                )
                self.assertEqual(conflict_status, 409)
                self.assertTrue((root / "second.md").is_file())

                unknown_status, _ = self._error(
                    f"{base}/api/v1/files/restore",
                    {"source_id": source_id, "operation_id": "missing"},
                    method="POST",
                )
                self.assertEqual(unknown_status, 404)
            finally:
                self._stop_server(server, thread)

    def test_restart_reconciles_interrupted_atomic_delete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, database, source_id = self._workspace(temp_dir)
            note = root / "interrupted.md"
            note.write_text("recover me", encoding="utf-8")
            scan_source(source_id, database_path=database)
            recovery_path = (
                Path(".morningbrief-trash")
                / "recovery-interrupted"
                / "interrupted.md"
            )
            recovery_target = root / recovery_path
            recovery_target.parent.mkdir(parents=True)
            content_hash = hash_file(note)
            with connect(database) as connection:
                connection.execute(
                    """
                    INSERT INTO file_recovery_operations
                      (id, request_id, data_source_id, relative_path,
                       recovery_path, content_hash, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                    """,
                    (
                        "recovery-interrupted",
                        "interrupted-request",
                        source_id,
                        "interrupted.md",
                        recovery_path.as_posix(),
                        content_hash,
                    ),
                )
            note.replace(recovery_target)

            server, thread, base = self._start_server(database)
            try:
                recoveries = self._get(
                    f"{base}/api/v1/file-recoveries?"
                    + urlencode({"source_id": source_id})
                )
                self.assertEqual(recoveries["recoveries"][0]["status"], "deleted")
                files = self._get(
                    f"{base}/api/v1/files?"
                    + urlencode({"source_id": source_id})
                )
                self.assertEqual(files["files"], [])
            finally:
                self._stop_server(server, thread)

            with connect(database) as connection:
                connection.execute(
                    """
                    UPDATE file_recovery_operations
                    SET status = 'restoring'
                    WHERE id = 'recovery-interrupted'
                    """
                )
            os.link(recovery_target, note)

            server, thread, base = self._start_server(database)
            try:
                preview = self._get(
                    f"{base}/api/v1/files?"
                    + urlencode(
                        {"source_id": source_id, "path": "interrupted.md"}
                    )
                )
                self.assertEqual(preview["file"]["content"], "recover me")
                with connect(database) as connection:
                    status = connection.execute(
                        """
                        SELECT status FROM file_recovery_operations
                        WHERE id = 'recovery-interrupted'
                        """
                    ).fetchone()["status"]
                self.assertEqual(status, "restored")
            finally:
                self._stop_server(server, thread)

    # File move/rename semantics are intentionally owned by Issue #65. This
    # matrix exercises the recovery contract without introducing a second move
    # implementation on the Issue #67 branch.

    @staticmethod
    def _workspace(temp_dir):
        root = Path(temp_dir) / "vault"
        root.mkdir()
        database = Path(temp_dir) / "app.sqlite3"
        initialize(database)
        source_id = register_source(
            "Vault", root, read_only=False, database_path=database
        )
        return root, database, source_id

    @staticmethod
    def _start_server(database):
        server = create_local_server(database_path=database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, f"http://127.0.0.1:{server.server_port}"

    @staticmethod
    def _stop_server(server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    def test_file_move_rejects_unsafe_cross_source_and_existing_targets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            original = root / "brief.md"
            original.write_text("# Brief", encoding="utf-8")
            (root / "existing.md").write_text("# Existing", encoding="utf-8")
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            import storage.data_sources as data_sources

            with patch.object(data_sources, "initialize"), patch.object(
                data_sources, "connect", side_effect=lambda path=None: connect(database)
            ):
                source_id = register_source("Vault", root)
                scan_source(source_id)

            server = create_local_server(database_path=database)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/api/v1/files"
                cases = [
                    (
                        {
                            "source_id": source_id,
                            "path": "brief.md",
                            "destination_path": "../outside.md",
                        },
                        400,
                        "invalid_relative_path",
                    ),
                    (
                        {
                            "source_id": source_id,
                            "path": "brief.md",
                            "destination_path": str((root / "absolute.md").resolve()),
                        },
                        400,
                        "invalid_relative_path",
                    ),
                    (
                        {
                            "source_id": source_id,
                            "path": str(original.resolve()),
                            "destination_path": "renamed.md",
                        },
                        400,
                        "invalid_relative_path",
                    ),
                    (
                        {
                            "source_id": source_id,
                            "destination_source_id": "another-source",
                            "path": "brief.md",
                            "destination_path": "moved.md",
                        },
                        400,
                        "cross_source_move_not_allowed",
                    ),
                    (
                        {
                            "source_id": source_id,
                            "path": "brief.txt",
                            "destination_path": "renamed.txt",
                        },
                        400,
                        "only_markdown_files_can_be_moved",
                    ),
                    (
                        {
                            "source_id": source_id,
                            "path": "brief.md",
                            "destination_path": "existing.md",
                        },
                        409,
                        "destination_exists",
                    ),
                ]
                for payload, expected_status, expected_error in cases:
                    with self.subTest(expected_error=expected_error):
                        error = self._patch_error(base, payload)
                        self.assertEqual(error.code, expected_status)
                        response = json.loads(error.read().decode("utf-8"))
                        self.assertEqual(response, {"error": expected_error})
                        self.assertNotIn(str(root), json.dumps(response))
                self.assertEqual("# Brief", original.read_text(encoding="utf-8"))
                self.assertEqual(
                    "# Existing",
                    (root / "existing.md").read_text(encoding="utf-8"),
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_recent_file_metadata_survives_api_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            first = root / "first.md"
            second = root / "second.md"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            os.utime(first, (1_700_000_000, 1_700_000_000))
            os.utime(second, (1_800_000_000, 1_800_000_000))
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            import storage.data_sources as data_sources

            with patch.object(data_sources, "initialize"), patch.object(
                data_sources, "connect", side_effect=lambda path=None: connect(database)
            ):
                source_id = register_source("Restart vault", root)
                scan_source(source_id)

            snapshots = []
            for _ in range(2):
                server = create_local_server(database_path=database)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    snapshots.append(
                        self._get(
                            f"http://127.0.0.1:{server.server_port}"
                            f"/api/v1/files?source_id={source_id}&sort=recent&limit=2"
                        )
                    )
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

            self.assertEqual(snapshots[0], snapshots[1])
            self.assertEqual(
                ["second.md", "first.md"],
                [item["relative_path"] for item in snapshots[0]["files"]],
            )

    def test_folder_sync_previews_then_copies_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            target = Path(temp_dir) / "target"
            source.mkdir()
            target.mkdir()
            (source / "new.md").write_text("new", encoding="utf-8")
            (source / "conflict.md").write_text("source", encoding="utf-8")
            (target / "conflict.md").write_text("target", encoding="utf-8")
            database = Path(temp_dir) / "app.sqlite3"
            initialize(database)
            source_id = register_source(
                "Source",
                source,
                read_only=False,
                database_path=database,
            )
            scan_source(source_id, database_path=database)
            server, thread, base = self._start_server(database)
            try:
                preview = self._post(
                    f"{base}/api/v1/folder-sync",
                    {
                        "source_id": source_id,
                        "target_root": str(target),
                        "apply": False,
                    },
                )["sync"]
                self.assertEqual(["new.md"], preview["added"])
                self.assertEqual(["conflict.md"], preview["conflicts"])
                self.assertFalse((target / "new.md").exists())

                applied = self._post(
                    f"{base}/api/v1/folder-sync",
                    {
                        "source_id": source_id,
                        "target_root": str(target),
                        "apply": True,
                    },
                )["sync"]
                self.assertEqual(["new.md"], applied["copied"])
                self.assertEqual(
                    "target",
                    (target / "conflict.md").read_text(encoding="utf-8"),
                )
                self.assertEqual(
                    "new", (target / "new.md").read_text(encoding="utf-8")
                )
                self.assertTrue(applied["target_source_id"])
                self.assertEqual(2, applied["indexed_files"])
            finally:
                self._stop_server(server, thread)

    @staticmethod
    def _get(url):
        with urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _request(url, payload, method):
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _patch(url, payload):
        return LocalFileApiTests._request(url, payload, "PATCH")

    @classmethod
    def _post(cls, url, payload):
        return cls._request(url, payload, "POST")

    @classmethod
    def _delete(cls, url, payload):
        return cls._request(url, payload, "DELETE")

    @staticmethod
    def _error(url, payload, *, method):
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            urlopen(request)
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                return exc.code, payload
            finally:
                exc.close()
        raise AssertionError("request unexpectedly succeeded")

    @classmethod
    def _patch_error(cls, url, payload):
        try:
            cls._patch(url, payload)
        except HTTPError as error:
            return error
        raise AssertionError("Expected PATCH request to fail")


if __name__ == "__main__":
    unittest.main()
