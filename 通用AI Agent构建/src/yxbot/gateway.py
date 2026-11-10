"""DeepSeek chat completions. Tool calls are optional; plain text still works."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse

from yxbot.config import Settings

VPN_HINT = "连不上内网网关。先确认 VPN，或运行仓库根目录的 setup_ds_hosts.ps1。"


class GatewayError(Exception):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: dict
    call_id: str = ""


@dataclass
class Turn:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


def rewrite_url_host(url: str, ip: str) -> tuple[str, str]:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise GatewayError(f"无法从 URL 解析主机: {url}")
    port = parsed.port
    netloc = f"{ip}:{port}" if port else ip
    return parsed._replace(netloc=netloc).geturl(), hostname


def _loads_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def extract_json_tool(content: str) -> ToolCall | None:
    text = (content or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    blob = fenced.group(1) if fenced else text
    if not blob.startswith("{"):
        return None
    try:
        obj = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or not obj.get("tool"):
        return None
    args = obj.get("args") or obj.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}
    return ToolCall(name=str(obj["tool"]), arguments=args)


def parse_response(data: dict) -> Turn:
    if not isinstance(data, dict):
        raise GatewayError("模型响应不是 JSON 对象")
    err = data.get("error")
    if isinstance(err, dict):
        raise GatewayError(str(err.get("message") or err))
    code = data.get("code")
    if code is not None and code != 0:
        raise GatewayError(f"DeepSeek code={code}")
    choices = data.get("choices") or []
    if not choices:
        raise GatewayError("DeepSeek 响应无 choices")
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    calls: list[ToolCall] = []
    for item in message.get("tool_calls") or []:
        fn = item.get("function") or {}
        name = str(fn.get("name") or "")
        if not name:
            continue
        calls.append(ToolCall(name=name, arguments=_loads_args(fn.get("arguments")), call_id=str(item.get("id") or "")))
    if not calls:
        embedded = extract_json_tool(content)
        if embedded:
            return Turn(content="", tool_calls=[embedded])
    if not content and not calls:
        raise GatewayError("模型没有返回正文")
    return Turn(content=content, tool_calls=calls)


def post_chat(url: str, api_key: str, payload: dict, timeout: int, extra_headers: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(err_text) if err_text else {}
        except json.JSONDecodeError:
            raise GatewayError(f"HTTP {exc.code}: {err_text[:400]}") from exc
        if isinstance(data, dict) and data.get("error"):
            err = data["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise GatewayError(f"HTTP {exc.code}: {message}")
        raise GatewayError(f"HTTP {exc.code}: {err_text[:400]}")
    except urllib.error.URLError as exc:
        raise GatewayError(f"连接失败: {exc.reason}\n{VPN_HINT}") from exc
    except TimeoutError as exc:
        raise GatewayError(f"超时（{timeout}s）") from exc


class DeepSeekGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> Turn:
        if not self.settings.configured:
            raise GatewayError("未配置 DEEPSEEK_API_KEY / DEEPSEEK_API_URL / DEEPSEEK_MODEL_ID")
        try:
            return self._complete(messages, tools)
        except GatewayError as exc:
            if tools and "tool" in str(exc).lower():
                return self._complete(messages, None)
            raise


class StreamAssembler:
    def __init__(self) -> None:
        self.content: list[str] = []
        self.calls: dict[int, dict] = {}

    def feed_line(self, line: str) -> str:
        text = line.strip()
        if not text.startswith("data:"):
            return ""
        data = text[5:].strip()
        if not data or data == "[DONE]":
            return ""
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return ""
        err = obj.get("error")
        if isinstance(err, dict):
            raise GatewayError(str(err.get("message") or err))
        choices = obj.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or choices[0].get("message") or {}
        piece = delta.get("content") or ""
        if piece:
            self.content.append(piece)
        for item in delta.get("tool_calls") or []:
            index = int(item.get("index") or 0)
            slot = self.calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
            if item.get("id"):
                slot["id"] = str(item["id"])
            function = item.get("function") or {}
            if function.get("name"):
                slot["name"] += str(function["name"])
            if function.get("arguments"):
                slot["arguments"] += str(function["arguments"])
        return piece

    def finish(self) -> Turn:
        content = "".join(self.content).strip()
        calls: list[ToolCall] = []
        for index in sorted(self.calls):
            slot = self.calls[index]
            if not slot["name"]:
                continue
            calls.append(ToolCall(slot["name"], _loads_args(slot["arguments"]), slot["id"]))
        if not calls:
            embedded = extract_json_tool(content)
            if embedded:
                return Turn(content="", tool_calls=[embedded])
        if not content and not calls:
            raise GatewayError("模型没有返回正文")
        return Turn(content=content, tool_calls=calls)


def _target(self) -> tuple[str, str, dict | None]:
    url = self.settings.api_url
    extra = None
    if self.settings.host_ip:
        url, host = rewrite_url_host(url, self.settings.host_ip)
        extra = {"Host": host}
    return url, self.settings.api_key, extra


def _payload(self, messages, tools, stream: bool, max_tokens: int) -> dict:
    payload = {
        "model": self.settings.model_id,
        "messages": messages,
        "stream": stream,
        "enable_thinking": False,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
    return payload


def _complete(self, messages: list[dict], tools: list[dict] | None, max_tokens: int = 2048) -> Turn:
    url, api_key, extra = self._target()
    data = post_chat(
        url,
        api_key,
        self._payload(messages, tools, stream=False, max_tokens=max_tokens),
        self.settings.timeout_sec,
        extra,
    )
    return parse_response(data)


def suggest_title(self, transcript_text: str) -> str:
    turn = self._complete(
        [
            {
                "role": "system",
                "content": "用不超过16个汉字总结对话标题。只输出标题本身，不要引号、书名号或句号。",
            },
            {"role": "user", "content": (transcript_text or "")[:1500]},
        ],
        None,
        max_tokens=32,
    )
    line = (turn.content or "").strip().splitlines()[0] if turn.content else ""
    return line.strip("「」\"'“” 。！？")


def iter_stream(self, messages: list[dict], tools: list[dict] | None = None):
    if not self.settings.configured:
        raise GatewayError("未配置 DEEPSEEK_API_KEY / DEEPSEEK_API_URL / DEEPSEEK_MODEL_ID")
    try:
        turn = yield from self._iter_stream(messages, tools)
    except GatewayError as exc:
        if tools and "tool" in str(exc).lower():
            turn = yield from self._iter_stream(messages, None)
        else:
            raise
    return turn


def _iter_stream(self, messages: list[dict], tools: list[dict] | None):
    url, api_key, extra = self._target()
    payload = self._payload(messages, tools, stream=True, max_tokens=2048)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
    }
    if extra:
        headers.update(extra)
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    assembler = StreamAssembler()
    try:
        response = urllib.request.urlopen(request, timeout=self.settings.timeout_sec)
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        raise GatewayError(f"HTTP {exc.code}: {err_text[:400]}") from exc
    except urllib.error.URLError as exc:
        raise GatewayError(f"连接失败: {exc.reason}\n{VPN_HINT}") from exc
    except TimeoutError as exc:
        raise GatewayError(f"超时（{self.settings.timeout_sec}s）") from exc
    try:
        peeked = response.peek() if hasattr(response, "peek") else b""
        if peeked.lstrip().startswith(b"{"):
            raw = response.read().decode("utf-8")
            turn = parse_response(json.loads(raw))
            if turn.content and not turn.tool_calls:
                yield turn.content
            return turn
        while True:
            line = response.readline()
            if not line:
                break
            delta = assembler.feed_line(line.decode("utf-8", errors="replace"))
            if delta:
                yield delta
    finally:
        response.close()
    return assembler.finish()


DeepSeekGateway._target = _target
DeepSeekGateway._payload = _payload
DeepSeekGateway._complete = _complete
DeepSeekGateway.suggest_title = suggest_title
DeepSeekGateway.iter_stream = iter_stream
DeepSeekGateway._iter_stream = _iter_stream
