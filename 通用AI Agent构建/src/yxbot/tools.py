"""Workspace tools. Write and shell are only called after the user allows them."""

from __future__ import annotations

import subprocess
from pathlib import Path

from yxbot.gateway import ToolCall

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
            "description": "读取工作目录内的文本文件",
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
    if call.name == "read_file":
        return f"读取 {args.get('path')}"
    if call.name == "list_dir":
        return f"列出 {args.get('path') or '.'}"
    return call.name


def run_tool(workspace: Path, call: ToolCall) -> str:
    try:
        if call.name == "list_dir":
            return _list_dir(workspace, call.arguments.get("path"))
        if call.name == "read_file":
            return _read_file(workspace, call.arguments.get("path"))
        if call.name == "write_file":
            return _write_file(workspace, call.arguments.get("path"), call.arguments.get("content"))
        if call.name == "run_command":
            return _run_command(workspace, call.arguments.get("command"))
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


def _read_file(workspace: Path, raw: str | None) -> str:
    if not raw:
        raise ToolError("缺少 path")
    path = resolve_inside(workspace, raw)
    if not path.is_file():
        raise ToolError(f"找不到文件 {raw}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > 20000:
        return text[:20000] + "\n…已截断"
    return text


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
