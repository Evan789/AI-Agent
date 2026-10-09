import tempfile
import unittest
from pathlib import Path

from yxbot.gateway import ToolCall
from yxbot.tools import ToolError, resolve_inside, run_tool


class ToolTests(unittest.TestCase):
    def test_rejects_path_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ToolError):
                resolve_inside(root, "../outside.txt")

    def test_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ToolError):
                resolve_inside(Path(tmp), str(Path(tmp) / "inner.txt"))

    def test_write_and_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = run_tool(root, ToolCall("write_file", {"path": "notes/a.txt", "content": "hello"}))
            self.assertIn("已写入", note)
            text = run_tool(root, ToolCall("read_file", {"path": "notes/a.txt"}))
            self.assertEqual(text, "hello")


if __name__ == "__main__":
    unittest.main()
