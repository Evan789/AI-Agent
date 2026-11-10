"""One agent loop for the window. Write and shell stop until the user allows them."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from yxbot.gateway import GatewayError, ToolCall, Turn
from yxbot.sessions import SessionError, SessionStore
from yxbot.tools import NEEDS_CONFIRM, TOOL_SCHEMAS, describe_call, run_tool

MAX_STEPS = 8
SYSTEM_PROMPT = (
    "你是 YXBot。用户在这台电脑上通过窗口和你交谈，工作范围是用户选定的文件夹。"
    "只在需要看文件、改文件或运行命令时使用工具。普通交流直接用中文回答，不要调用工具。"
    "读取 Word（.docx）和 PDF 时只能调用 read_document，不要用命令行安装或探测 PDF、Word 库。"
    "read_document 按页返回正文。某一页若写着未提取到文字，那一页是图片，不要把乱码当成正文，也不要改用命令行再读。"
    "纯文本 .txt 和 .md 可以用 read_file 或 read_document。"
    "询问空气质量或 AQI 时调用 query_china_weather。只引用工具返回的数字。"
    "该接口只有中国天气网当天的逐小时数据。若结果写明不能查询该日期，就如实说明，不要编造历史空气质量。"
    "不要编造没有读到的文件内容。"
    "写入文件和运行命令会由用户点允许后才执行，你提出调用即可。"
    "如果不能使用 tools 字段，需要调用工具时只输出一个 JSON 对象："
    '{"tool":"工具名","args":{...}}，不要加解释。'
)


class AgentError(Exception):
    pass


class Agent:
    def __init__(self, gateway, workspace: Path, store: SessionStore | None = None) -> None:
        self.gateway = gateway
        self.workspace = workspace
        self.store = store
        self.session_id: str | None = None
        self.session_title = ""
        self.title_locked = False
        self.history: list[dict] = []
        self.transcript: list[dict] = []
        self.terminal: list[str] = []
        self.pending: ToolCall | None = None

    def state(self) -> dict:
        pending = None
        if self.pending:
            pending = {"name": self.pending.name, "text": describe_call(self.pending)}
        sessions = self.store.list_sessions() if self.store else []
        return {
            "workspace": str(self.workspace),
            "transcript": list(self.transcript),
            "terminal": list(self.terminal[-80:]),
            "pending": pending,
            "session_id": self.session_id,
            "sessions": sessions,
        }

    def set_workspace(self, path: Path) -> None:
        if self.pending:
            raise AgentError("请先允许或拒绝当前操作")
        if not path.is_dir():
            raise AgentError("工作目录不存在")
        self.workspace = path.resolve()

    def title(self) -> str:
        if self.session_title.strip():
            return self.session_title.strip()[:40]
        for item in self.transcript:
            if item.get("who") == "user" and str(item.get("text") or "").strip():
                text = " ".join(str(item["text"]).split())
                return text[:24]
        return "新对话"

    def _clear(self) -> None:
        self.history.clear()
        self.transcript.clear()
        self.terminal.clear()
        self.pending = None
        self.session_id = None
        self.session_title = ""
        self.title_locked = False

    def start_new(self) -> None:
        if self.store and self.session_id and (self.transcript or self.history):
            self.persist()
        self._clear()

    def reset(self) -> None:
        self.start_new()

    def open_session(self, session_id: str) -> None:
        if not self.store:
            raise AgentError("没有会话存储")
        if self.session_id and self.session_id != session_id and (self.transcript or self.history):
            self.persist()
        try:
            self._apply(self.store.load(session_id))
        except SessionError as exc:
            raise AgentError(str(exc)) from exc

    def delete_session(self, session_id: str) -> None:
        if not self.store:
            raise AgentError("没有会话存储")
        try:
            self.store.delete(session_id)
        except SessionError as exc:
            raise AgentError(str(exc)) from exc
        if self.session_id != session_id:
            return
        self._clear()
        latest = self.store.latest()
        if latest:
            self._apply(latest)

    def rename(self, session_id: str, name: str) -> None:
        if not self.store:
            raise AgentError("没有会话存储")
        cleaned = " ".join(name.split())[:40] or "新对话"
        if session_id == self.session_id:
            self.session_title = cleaned
            self.title_locked = True
            self.persist()
            return
        try:
            record = self.store.load(session_id)
        except SessionError as exc:
            raise AgentError(str(exc)) from exc
        record["title"] = cleaned
        record["title_locked"] = True
        self.store.save(record)

    def persist(self) -> None:
        if not self.store:
            return
        if not self.session_id:
            self.session_id = self.store.new_id()
        pending = None
        if self.pending:
            pending = {
                "name": self.pending.name,
                "arguments": self.pending.arguments,
                "call_id": self.pending.call_id,
            }
        self.store.save(
            {
                "id": self.session_id,
                "title": self.title(),
                "title_locked": self.title_locked,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "history": self.history,
                "transcript": self.transcript,
                "terminal": self.terminal,
                "pending": pending,
            }
        )

    def _apply(self, record: dict) -> None:
        self.session_id = str(record.get("id") or "")
        self.session_title = str(record.get("title") or "")
        self.title_locked = bool(record.get("title_locked"))
        self.history = list(record.get("history") or [])
        self.transcript = list(record.get("transcript") or [])
        self.terminal = list(record.get("terminal") or [])
        pending = record.get("pending")
        if isinstance(pending, dict) and pending.get("name"):
            self.pending = ToolCall(
                str(pending["name"]),
                pending.get("arguments") or {},
                str(pending.get("call_id") or ""),
            )
        else:
            self.pending = None

    def user_say(self, text: str) -> None:
        message = text.strip()
        if not message:
            raise AgentError("请输入内容")
        if self.pending:
            raise AgentError("请先允许或拒绝当前操作")
        self.history.append({"role": "user", "content": message})
        self.transcript.append({"who": "user", "text": message})
        for _event in self._advance():
            pass
        self._refresh_title()
        self.persist()

    def events_for_user(self, text: str):
        message = text.strip()
        if not message:
            raise AgentError("请输入内容")
        if self.pending:
            raise AgentError("请先允许或拒绝当前操作")
        self.history.append({"role": "user", "content": message})
        self.transcript.append({"who": "user", "text": message})
        yield from self._advance()
        self._refresh_title()
        self.persist()
        yield {"type": "done", "state": self.state()}

    def confirm(self, allow: bool) -> None:
        for _event in self.events_for_confirm(allow):
            pass

    def events_for_confirm(self, allow: bool):
        call = self.pending
        if call is None:
            raise AgentError("没有待确认的操作")
        self.pending = None
        if allow:
            result = run_tool(self.workspace, call)
        else:
            result = "用户拒绝了这个操作。"
        self._record_tool(call, result)
        yield {"type": "tool", "text": f"{call.name}：{result[:500]}"}
        yield from self._advance()
        self._refresh_title()
        self.persist()
        yield {"type": "done", "state": self.state()}

    def _refresh_title(self) -> None:
        if self.title_locked:
            return
        suggest = getattr(self.gateway, "suggest_title", None)
        if not suggest:
            return
        lines = []
        for item in self.transcript:
            if item.get("who") in {"user", "assistant"} and str(item.get("text") or "").strip():
                lines.append(str(item["text"])[:300])
        if len(lines) < 2:
            return
        try:
            title = suggest("\n".join(lines[-6:]))
        except GatewayError:
            return
        cleaned = " ".join(str(title or "").replace("\n", " ").split())
        cleaned = cleaned.strip("「」\"'“” 。！？")
        if cleaned:
            self.session_title = cleaned[:16]

    def _messages_for_model(self) -> list[dict]:
        return [{"role": "system", "content": SYSTEM_PROMPT}, *self.history]

    def _stream_model(self):
        if hasattr(self.gateway, "iter_stream"):
            generator = self.gateway.iter_stream(self._messages_for_model(), TOOL_SCHEMAS)
            while True:
                try:
                    piece = next(generator)
                except StopIteration as stop:
                    return stop.value or Turn("")
                if piece:
                    yield {"type": "delta", "text": piece}
        turn = self.gateway.complete(self._messages_for_model(), TOOL_SCHEMAS)
        if turn.content and not turn.tool_calls:
            yield {"type": "delta", "text": turn.content}
        return turn

    def _advance(self):
        for _ in range(MAX_STEPS):
            try:
                turn = yield from self._stream_model()
            except GatewayError as exc:
                self.transcript.append({"who": "assistant", "text": str(exc)})
                yield {"type": "error", "detail": str(exc)}
                return
            if not isinstance(turn, Turn):
                self.transcript.append({"who": "assistant", "text": "模型返回无法识别"})
                return
            if turn.tool_calls:
                call = turn.tool_calls[0]
                self.history.append({"role": "assistant", "content": turn.content or f"调用 {call.name}"})
                if call.name in NEEDS_CONFIRM:
                    self.pending = call
                    notice = "需要你确认后才会执行：\n" + describe_call(call)
                    self.transcript.append({"who": "assistant", "text": notice})
                    yield {"type": "pending", "text": notice}
                    return
                result = run_tool(self.workspace, call)
                self._record_tool(call, result)
                yield {"type": "tool", "text": f"{call.name}：{result[:500]}"}
                continue
            text = turn.content or "（没有回复）"
            self.history.append({"role": "assistant", "content": text})
            self.transcript.append({"who": "assistant", "text": text})
            return
        notice = "这一轮步数已用完，停下来了。"
        self.transcript.append({"who": "assistant", "text": notice})
        yield {"type": "delta", "text": notice}

    def _record_tool(self, call: ToolCall, result: str) -> None:
        self.terminal.append(describe_call(call).split("\n", 1)[0])
        self.terminal.append(result[:2000])
        self.history.append({"role": "user", "content": f"工具 {call.name} 结果：\n{result}"})
        self.transcript.append({"who": "tool", "text": f"{call.name}：{result[:500]}"})
