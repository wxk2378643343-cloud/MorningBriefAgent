import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from core.application.local_api import create_local_server
from storage.data_sources import register_source, scan_source
from storage.sqlite import connect, initialize


class LocalFileApiTests(unittest.TestCase):
    def test_health_endpoint_is_local_service_probe(self):
        server = create_local_server()
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
                base = f"http://127.0.0.1:{server.server_port}"
                sources = self._get(f"{base}/api/v1/data-sources")
                files = self._get(f"{base}/api/v1/files?source_id={source_id}")
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
                self.assertEqual(sources["sources"][0]["name"], "Vault")
                self.assertEqual(files["files"][0]["relative_path"], "brief.md")
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

    @staticmethod
    def _get(url):
        with urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _post(url, payload):
        from urllib.request import Request

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _patch(url, payload):
        from urllib.request import Request

        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PATCH",
        )
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    @classmethod
    def _patch_error(cls, url, payload):
        try:
            cls._patch(url, payload)
        except HTTPError as error:
            return error
        raise AssertionError("Expected PATCH request to fail")


if __name__ == "__main__":
    unittest.main()
