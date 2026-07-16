import tempfile
import unittest
from pathlib import Path

from core.paths import resolve_path


class CorePathTests(unittest.TestCase):
    def test_maps_virtual_workspace_into_session(self):
        with tempfile.TemporaryDirectory() as temporary_root:
            session = Path(temporary_root) / "output" / "session-1"
            session.mkdir(parents=True)

            result = resolve_path("/home/daytona/workspace/report.md", str(session))

            self.assertEqual(Path(result), session / "report.md")

    def test_removes_repeated_session_prefix(self):
        with tempfile.TemporaryDirectory() as temporary_root:
            session = Path(temporary_root) / "output" / "session-1"
            session.mkdir(parents=True)

            result = resolve_path("output/session-1/report.md", str(session))

            self.assertEqual(Path(result), session / "report.md")

    def test_rejects_paths_outside_session(self):
        with tempfile.TemporaryDirectory() as temporary_root:
            root = Path(temporary_root)
            session = root / "output" / "session-1"
            session.mkdir(parents=True)

            with self.assertRaisesRegex(ValueError, "超出当前会话目录"):
                resolve_path(str(root / "private.txt"), str(session))


if __name__ == "__main__":
    unittest.main()
