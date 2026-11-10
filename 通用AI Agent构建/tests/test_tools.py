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

    def test_read_document_text_pdf_by_page(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = pymupdf.open()
            first = document.new_page()
            first.insert_text((72, 72), "alpha page")
            second = document.new_page()
            second.insert_text((72, 72), "beta page")
            document.save(root / "note.pdf")
            document.close()
            both = run_tool(root, ToolCall("read_document", {"path": "note.pdf"}))
            self.assertIn("第 1 页", both)
            self.assertIn("alpha page", both)
            self.assertIn("第 2 页", both)
            self.assertIn("beta page", both)
            only_second = run_tool(
                root,
                ToolCall("read_document", {"path": "note.pdf", "start_page": 2, "end_page": 2}),
            )
            self.assertIn("beta page", only_second)
            self.assertNotIn("alpha page", only_second)

    def test_read_document_marks_empty_pdf_page(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = pymupdf.open()
            document.new_page()
            document.save(root / "scan.pdf")
            document.close()
            text = run_tool(root, ToolCall("read_document", {"path": "scan.pdf"}))
            self.assertIn("第 1 页", text)
            self.assertIn("本页是图片，未提取到文字", text)

    def test_read_document_rejects_path_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = run_tool(root, ToolCall("read_document", {"path": "../secret.pdf"}))
            self.assertIn("路径超出工作目录", text)

    def test_read_document_docx_page_break(self):
        from docx import Document
        from docx.enum.text import WD_BREAK

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = Document()
            document.add_paragraph("第一页正文")
            document.paragraphs[0].add_run().add_break(WD_BREAK.PAGE)
            document.add_paragraph("第二页正文")
            document.save(root / "note.docx")
            text = run_tool(root, ToolCall("read_document", {"path": "note.docx"}))
            self.assertIn("第 1 页", text)
            self.assertIn("第一页正文", text)
            self.assertIn("第 2 页", text)
            self.assertIn("第二页正文", text)


if __name__ == "__main__":
    unittest.main()
