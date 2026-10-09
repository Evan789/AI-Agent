"""One agent loop for the window. Write and shell stop until the user allows them."""

from __future__ import annotations

from pathlib import Path

from yxbot.gateway import GatewayError, ToolCall, Turn
from yxbot.tools import NEEDS_CONFIRM, TOOL_SCHEMAS, describe_call, run_tool

MAX_STEPS = 8
SYSTEM_PROMPT = (
    "你是 YXBot。用户在这台电脑上通过窗口和你交谈，工作范围是用户选定的文件夹。"
    "只在需要看文件、改文件或运行命令时使用工具。普通交流直接用中文回答，不要调用工具。"
    "不要编造没有读到的文件内容。"
    "写入文件和运行命令会由用户点允许后才执行，你提出调用即可。"
    "如果不能使用 tools 字段，需要调用工具时只输出一个 JSON 对象："
    '{"tool":"工具名","args":{...}}，不要加解释。'
)


class AgentError(Exception):
    pass


class Agent:
    def __init__(self, gateway, workspace: Path) -> None:
        self.gateway = gateway
        self.workspace = workspace
        self.history: list[dict] = []
        self.transcript: list[dict] = []
        self.terminal: list[str] = []
        self.pending: ToolCall | None = None

    def state(self) -> dict:
        pending = None
        if self.pending:
            pending = {"name": self.pending.name, "text": describe_call(self.pending)}
        return {
            "workspace": str(self.workspace),
            "transcript": list(self.transcript),
            "terminal": list(self.terminal[-80:]),
            "pending": pending,
        }

    def set_workspace(self, path: Path) -> None:
        if self.pending:
            raise AgentError("请先允许或拒绝当前操作")
        if not path.is_dir():
            raise AgentError("工作目录不存在")
        self.workspace = path.resolve()

    def reset(self) -> None:
        self.history.clear()
        self.transcript.clear()
        self.terminal.clear()
        self.pending = None

    def user_say(self, text: str) -> None:
        message = text.strip()
        if not message:
            raise AgentError("请输入内容")
        if self.pending:
            raise AgentError("请先允许或拒绝当前操作")
        self.history.append({"role": "user", "content": message})
        self.transcript.append({"who": "user", "text": message})
        self._advance()

    def confirm(self, allow: bool) -> None:
        call = self.pending
        if call is None:
            raise AgentError("没有待确认的操作")
        self.pending = None
        if allow:
            result = run_tool(self.workspace, call)
        else:
            result = "用户拒绝了这个操作。"
        self._record_tool(call, result)
        self._advance()

    def _messages_for_model(self) -> list[dict]:
        return [{"role": "system", "content": SYSTEM_PROMPT}, *self.history]

    def _advance(self) -> None:
        for _ in range(MAX_STEPS):
            try:
                turn = self.gateway.complete(self._messages_for_model(), TOOL_SCHEMAS)
            except GatewayError as exc:
                self.transcript.append({"who": "assistant", "text": str(exc)})
                return
            if not isinstance(turn, Turn):
                self.transcript.append({"who": "assistant", "text": "模型返回无法识别"})
                return
            if turn.tool_calls:
                call = turn.tool_calls[0]
                self.history.append({"role": "assistant", "content": turn.content or f"调用 {call.name}"})
                if call.name in NEEDS_CONFIRM:
                    self.pending = call
                    self.transcript.append({"who": "assistant", "text": "需要你确认后才会执行：\n" + describe_call(call)})
                    return
                result = run_tool(self.workspace, call)
                self._record_tool(call, result)
                continue
            text = turn.content or "（没有回复）"
            self.history.append({"role": "assistant", "content": text})
            self.transcript.append({"who": "assistant", "text": text})
            return
        self.transcript.append({"who": "assistant", "text": "这一轮步数已用完，停下来了。"})

    def _record_tool(self, call: ToolCall, result: str) -> None:
        self.terminal.append(describe_call(call).split("\n", 1)[0])
        self.terminal.append(result[:2000])
        self.history.append({"role": "user", "content": f"工具 {call.name} 结果：\n{result}"})
        self.transcript.append({"who": "tool", "text": f"{call.name}：{result[:500]}"})
