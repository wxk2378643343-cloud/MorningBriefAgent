import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from unittest.mock import patch

from core.application.local_api import create_local_server
from storage.data_sources import register_source, scan_source
from storage.sqlite import connect, initialize


class LocalFileApiTests(unittest.TestCase):
    def test_sources_and_files_are_readable_as_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            (root / "brief.md").write_text("# Brief", encoding="utf-8")
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
                self.assertEqual(sources["sources"][0]["name"], "Vault")
                self.assertEqual(files["files"][0]["relative_path"], "brief.md")
                self.assertEqual(preview["file"]["content"], "# Brief")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    @staticmethod
    def _get(url):
        with urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
