"""Workspace tools. Write and shell are only called after the user allows them."""

from __future__ import annotations

import subprocess
from pathlib import Path

from yxbot.gateway import ToolCall
from yxbot.weather_cn import WeatherError, query_aqi

NEEDS_CONFIRM = {"write_file", "run_command"}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出工作目录中的文件和子目录",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "相对工作目录的路径，默认 ."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作目录内的 .txt 或 .md。Word 和 PDF 请用 read_document。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document",
            "description": "按页读取工作目录内的 .txt、.md、.docx 或带文字层的 .pdf。扫描页会标明未提取到文字。不要用命令行读取 Word 或 PDF。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_page": {"type": "integer", "description": "起始页，从 1 开始"},
                    "end_page": {"type": "integer", "description": "结束页，含本页"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入工作目录内的文本文件。调用后会等用户确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在工作目录中执行一条命令。调用后会等用户确认。",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_china_weather",
            "description": "只读查询中国天气网当天的城市空气质量。不能查历史日期，不要用命令行或网页代替。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，例如南昌"},
                    "date": {"type": "string", "description": "可选，YYYY-MM-DD。不是今天会说明无法查询"},
                },
                "required": ["city"],
            },
        },
    },
]


class ToolError(Exception):
    pass


def resolve_inside(workspace: Path, raw: str | None) -> Path:
    text = (raw or ".").strip() or "."
    candidate = Path(text)
    if candidate.is_absolute():
        raise ToolError("只允许工作目录内的相对路径")
    root = workspace.resolve()
    target = (root / candidate).resolve()
    if target != root and root not in target.parents:
        raise ToolError("路径超出工作目录")
    return target


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def describe_call(call: ToolCall) -> str:
    args = call.arguments or {}
    if call.name == "write_file":
        content = str(args.get("content") or "")
        preview = content[:500]
        return f"写入 {args.get('path') or '（未给路径）'}\n\n{preview}"
    if call.name == "run_command":
        return f"执行命令：{args.get('command') or '（空命令）'}"
    if call.name == "query_china_weather":
        return f"查询中国天气网 {args.get('city') or ''}"
    if call.name == "read_file":
        return f"读取 {args.get('path')}"
    if call.name == "read_document":
        span = ""
        if args.get("start_page") or args.get("end_page"):
            span = f" 第 {args.get('start_page') or 1}-{args.get('end_page') or '末'} 页"
        return f"读取文档 {args.get('path')}{span}"
    if call.name == "list_dir":
        return f"列出 {args.get('path') or '.'}"
    return call.name


def run_tool(workspace: Path, call: ToolCall) -> str:
    try:
        if call.name == "list_dir":
            return _list_dir(workspace, call.arguments.get("path"))
        if call.name == "read_file":
            return _read_file(workspace, call.arguments.get("path"))
        if call.name == "read_document":
            return _read_document(
                workspace,
                call.arguments.get("path"),
                call.arguments.get("start_page"),
                call.arguments.get("end_page"),
            )
        if call.name == "write_file":
            return _write_file(workspace, call.arguments.get("path"), call.arguments.get("content"))
        if call.name == "run_command":
            return _run_command(workspace, call.arguments.get("command"))
        if call.name == "query_china_weather":
            try:
                return query_aqi(str(call.arguments.get("city") or ""), call.arguments.get("date"))
            except WeatherError as exc:
                return str(exc)
        return f"未知工具 {call.name}"
    except ToolError as exc:
        return str(exc)


def _list_dir(workspace: Path, raw: str | None) -> str:
    path = resolve_inside(workspace, raw)
    if not path.exists():
        raise ToolError(f"找不到目录 {raw or '.'}")
    if not path.is_dir():
        raise ToolError(f"不是目录 {raw}")
    names = sorted(item.name + ("/" if item.is_dir() else "") for item in path.iterdir())
    if not names:
        return "（空目录）"
    shown = names[:200]
    tail = "\n…还有更多" if len(names) > 200 else ""
    return "\n".join(shown) + tail


_TEXT_LIMIT = 20000
_EMPTY_PAGE = "本页是图片，未提取到文字"


def _read_file(workspace: Path, raw: str | None) -> str:
    if not raw:
        raise ToolError("缺少 path")
    path = resolve_inside(workspace, raw)
    if not path.is_file():
        raise ToolError(f"找不到文件 {raw}")
    suffix = path.suffix.lower()
    if suffix in {".pdf", ".docx"}:
        return _read_document(workspace, raw, None, None)
    if suffix == ".doc":
        raise ToolError("不支持旧版 .doc，请另存为 .docx")
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > _TEXT_LIMIT:
        return text[:_TEXT_LIMIT] + "\n…已截断"
    return text


def _page_number(value, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ToolError(f"{name} 必须是页码") from None
    if number < 1:
        raise ToolError(f"{name} 必须从 1 开始")
    return number


def _format_pages(pages: list[tuple[int, str]]) -> str:
    blocks: list[str] = []
    used = 0
    for index, (number, text) in enumerate(pages):
        body = text.strip() or _EMPTY_PAGE
        block = f"第 {number} 页\n{body}"
        if used and used + len(block) > _TEXT_LIMIT:
            rest = pages[index][0]
            blocks.append(f"…已截断，未继续第 {rest} 页及之后")
            break
        if len(block) > _TEXT_LIMIT:
            block = block[:_TEXT_LIMIT] + "\n…已截断"
        blocks.append(block)
        used += len(block) + 2
    return "\n\n".join(blocks)


def _read_document(workspace: Path, raw: str | None, start_page, end_page) -> str:
    if not raw:
        raise ToolError("缺少 path")
    path = resolve_inside(workspace, raw)
    if not path.is_file():
        raise ToolError(f"找不到文件 {raw}")
    suffix = path.suffix.lower()
    if suffix == ".doc":
        raise ToolError("不支持旧版 .doc，请另存为 .docx")
    if suffix == ".pdf":
        pages = _pdf_pages(path)
    elif suffix == ".docx":
        pages = _docx_pages(path)
    elif suffix in {".txt", ".md"}:
        pages = [(1, path.read_text(encoding="utf-8", errors="replace"))]
    else:
        raise ToolError("read_document 只读取 txt、md、docx 和 pdf")
    start = _page_number(start_page, "start_page") or 1
    end = _page_number(end_page, "end_page") or len(pages)
    if start > end:
        raise ToolError("起始页不能大于结束页")
    if start > len(pages):
        raise ToolError(f"超出页数，这份文档共 {len(pages)} 页")
    end = min(end, len(pages))
    selected = [(number, text) for number, text in pages if start <= number <= end]
    return _format_pages(selected)


def _pdf_pages(path: Path) -> list[tuple[int, str]]:
    try:
        import pymupdf
    except ImportError as exc:
        raise ToolError("未安装 PDF 读取组件") from exc
    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise ToolError(f"无法读取该 PDF：{exc}") from exc
    pages: list[tuple[int, str]] = []
    try:
        for index, page in enumerate(document, start=1):
            pages.append((index, page.get_text("text") or ""))
    finally:
        document.close()
    return pages


def _docx_pages(path: Path) -> list[tuple[int, str]]:
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise ToolError("未安装 Word 读取组件") from exc
    try:
        document = Document(str(path))
    except Exception as exc:
        raise ToolError(f"无法读取该 Word：{exc}") from exc
    chunks = [""]
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            paragraph = Paragraph(child, document)
            chunks[-1] += paragraph.text + "\n"
            if 'w:type="page"' in paragraph._p.xml:
                chunks.append("")
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            rows = []
            for row in table.rows:
                rows.append(" | ".join(cell.text.strip() for cell in row.cells))
            chunks[-1] += "\n".join(rows) + "\n"
    return [(index, text) for index, text in enumerate(chunks, start=1)]


def _write_file(workspace: Path, raw: str | None, content) -> str:
    if not raw:
        raise ToolError("缺少 path")
    path = resolve_inside(workspace, raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("" if content is None else str(content), encoding="utf-8")
    return f"已写入 {raw}，{path.stat().st_size} 字节"


def _run_command(workspace: Path, command) -> str:
    text = str(command or "").strip()
    if not text:
        raise ToolError("命令是空的")
    if len(text) > 500:
        raise ToolError("命令过长")
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            text,
            shell=True,
            cwd=workspace,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "命令超时（30 秒），已停止"
    out = _decode(completed.stdout)
    err = _decode(completed.stderr)
    body = (out + ("\n" + err if err else "")).strip()
    if len(body) > 8000:
        body = body[:8000] + "\n…已截断"
    return f"退出码 {completed.returncode}\n{body or '（无输出）'}"
