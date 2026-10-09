"""DeepSeek v4 via the intranet compatible-mode gateway (VPN required).

Protocol matches AI Agent/test_deepseek_api.py:
- Auth: Bearer AppKey
- Success: top-level code == 0 (if present)
- system only on messages[0]; last message must be user
"""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Literal
from urllib.parse import urlparse

from agentos.gateway.base import Decision, DecisionKind, GenerateResponse

from aqagent.config import Settings
from aqagent.constants import ANALYZERS, POLICY
from aqagent.tools.schema import STAGE_TOOL_NAMES, TOOL_SCHEMAS

CHAT_SYSTEM = (
    "你是大气环境诊断助手的答疑口，不是分析器调度员。"
    "只根据用户消息里的上次分析JSON回答。没有JSON或 episode 为 null 时，说明还没做分析，并提示可以说「分析某城市 日期 的跷跷板」。"
    "不要编造JSON没有的数字或物种。不要调用或假装已运行分析器。200字以内，中文。"
)

SUMMARIZE_SYSTEM = (
    "你是大气环境分析记录员，不是发挥常识的顾问。"
    "只复述用户消息里工具JSON已写明的内容。400字以内，中文，不要输出JSON。"
    "固定四段标题：核心结论；结果中的因子；本次未给出；管控建议。"
    "「结果中的因子」只能出现 JSON 里出现过的污染物、气象量、状态字段。"
    "「本次未给出」必须只抄 JSON 字段 not_given 的原文，一个字都不要加减。"
    "不要列举任何化学物种或前体物缩写。"
    "不要点名结果 JSON 中未出现的化学物种或前体物。"
    "禁止编造天气过程、异常事件、未给出的浓度或相关系数。"
    "管控建议只能改写 JSON 中的 management_implication 或同等字段，不要另开化学机制。"
    "数字只能抄 JSON 中的数字。"
    "analyzer_catalog 的 name/desc 可以用来解释分析器在测什么，但不能据此引入 catalog 未写的物种。"
    "primary_source=default 必须声明演示数据、不可用于决策；public 只写数据来自公开接口，不要升格为站点实测。"
)

_EVIDENCE_KEYS = (
    "analyzers_run",
    "analyzer_count",
    "full_suite",
    "primary_source",
    "sample_count",
    "warnings",
    "summaries",
)


def _not_given(ids: list, summaries: dict | None) -> str:
    bodies = summaries or {}
    missing = []
    for i in ids or []:
        slim = bodies.get(i)
        if not isinstance(slim, dict) or not slim:
            missing.append(i)
    if missing:
        return "、".join(missing) + " 无有效结果"
    return "无"


def _catalog_for(ids: list) -> list[dict]:
    by_id = {a["id"]: a for a in ANALYZERS}
    cards = []
    for i in ids or []:
        a = by_id.get(i)
        if a:
            cards.append({"id": a["id"], "name": a["name"], "desc": a["desc"]})
    return cards


def analysis_evidence(goal: str, result: dict) -> dict:
    ids = result.get("analyzers_run") or []
    body = {k: result.get(k) for k in _EVIDENCE_KEYS if result.get(k) not in (None, [], {})}
    return {
        "goal": goal,
        "tool": "run_analysis",
        "not_given": _not_given(ids, result.get("summaries")),
        "analyzer_catalog": _catalog_for(ids),
        "result": body,
    }


def _evidence_json(goal: str, result: dict) -> str:
    raw = json.dumps(analysis_evidence(goal, result), ensure_ascii=False, default=str)
    if len(raw) > 4000:
        return raw[:4000] + "…"
    return raw


VPN_HINT = (
    "DeepSeek 网关需要在既定 VPN / 内网下访问。检查：1) 已连 VPN；"
    "2) ping ds.local.ai 或设置 DEEPSEEK_HOST_IP；3) 未改用公共 DNS。"
)


class DeepSeekError(Exception):
    def __init__(self, message: str, *, vpn_likely: bool = False):
        self.vpn_likely = vpn_likely
        super().__init__(message)


def rewrite_url_host(url: str, ip: str) -> tuple[str, str]:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise DeepSeekError(f"无法从 URL 解析主机: {url}")
    port = parsed.port
    netloc = f"{ip}:{port}" if port else ip
    return parsed._replace(netloc=netloc).geturl(), hostname


def parse_decision(text: str) -> Decision:
    raw = (text or "").strip()
    if not raw:
        return Decision(kind=DecisionKind.final, message="")
    candidate = raw
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fenced:
        candidate = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", raw, re.S)
        if brace:
            candidate = brace.group(0)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return Decision(kind=DecisionKind.final, message=raw)
    if not isinstance(data, dict):
        return Decision(kind=DecisionKind.final, message=raw)
    kind = str(data.get("kind") or "")
    thought = str(data.get("thought") or "")
    if kind == "tool_call":
        name = str(data.get("name") or "")
        args = data.get("args") if isinstance(data.get("args"), dict) else {}
        return Decision(kind=DecisionKind.tool_call, name=name, args=args, thought=thought)
    if kind == "final":
        return Decision(kind=DecisionKind.final, message=str(data.get("message") or raw), thought=thought)
    return Decision(kind=DecisionKind.final, message=raw)


def _tool_prompt() -> str:
    specs = json.dumps(
        [TOOL_SCHEMAS[n] for n in STAGE_TOOL_NAMES if n in TOOL_SCHEMAS],
        ensure_ascii=False,
    )
    return f"{POLICY}\nAllowed tools JSON: {specs}"


class DeepSeekGateway:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def health(self) -> dict:
        return {
            "ok": self.settings.llm_configured,
            "backend": "deepseek",
            "gpu_required": False,
            "vertical": "air_quality",
            "offline_mode": False,
            "model": self.settings.deepseek_model_id or None,
            "vpn_required": True,
            "hint": None if self.settings.llm_configured else "未配置 DEEPSEEK_*，见 AI Agent/.env.example",
            "loaded": [self.settings.deepseek_model_id] if self.settings.deepseek_model_id else [],
        }

    def generate(
        self,
        role: Literal["chat", "extract", "embed", "caption", "asr"],
        prompt: str = "",
    ) -> GenerateResponse:
        _ = role
        content = self.complete(
            [
                {"role": "system", "content": _tool_prompt()},
                {"role": "user", "content": prompt or "（空）"},
            ]
        )
        decision = parse_decision(content)
        return GenerateResponse(
            model_id=self.settings.deepseek_model_id or "deepseek",
            decision=decision,
            text=content,
        )

    def summarize_analysis(self, goal: str, result: dict) -> str:
        """Human diagnosis from tool JSON. Does not select or run tools."""
        user = (
            "按系统要求写四段摘要。只使用下列JSON。"
            "「本次未给出」只抄 not_given，不要补浓度或气象。\n"
            f"{_evidence_json(goal, result)}"
        )
        return self.complete(
            [
                {"role": "system", "content": SUMMARIZE_SYSTEM},
                {"role": "user", "content": user},
            ]
        )

    def chat_about(self, goal: str, evidence: dict) -> str:
        raw = json.dumps(evidence, ensure_ascii=False, default=str)
        if len(raw) > 3500:
            raw = raw[:3500] + "…"
        user = f"用户问：{goal}\n上次分析JSON：{raw}"
        return self.complete(
            [
                {"role": "system", "content": CHAT_SYSTEM},
                {"role": "user", "content": user},
            ]
        )

    def complete(self, messages: list[dict]) -> str:
        if not self.settings.llm_configured:
            raise DeepSeekError("未配置 DEEPSEEK_API_KEY / DEEPSEEK_API_URL / DEEPSEEK_MODEL_ID")
        url = self.settings.deepseek_api_url
        extra_headers: dict[str, str] = {}
        if self.settings.deepseek_host_ip:
            url, original_host = rewrite_url_host(url, self.settings.deepseek_host_ip)
            extra_headers["Host"] = original_host
        payload = {
            "model": self.settings.deepseek_model_id,
            "messages": messages,
            "stream": False,
            "enable_thinking": self.settings.deepseek_enable_thinking,
            "max_tokens": 2048,
        }
        data = post_chat(
            url,
            self.settings.deepseek_api_key,
            payload,
            timeout=self.settings.deepseek_timeout_sec,
            extra_headers=extra_headers or None,
        )
        if data.get("error"):
            err = data["error"]
            raise DeepSeekError(str(err.get("message") or err))
        code = data.get("code")
        if code is not None and code != 0:
            raise DeepSeekError(f"DeepSeek code={code}: {json.dumps(data, ensure_ascii=False)[:400]}")
        choices = data.get("choices") or []
        if not choices:
            raise DeepSeekError("DeepSeek 响应无 choices")
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise DeepSeekError("DeepSeek message.content 为空")
        return content


def diagnose_host(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        raise DeepSeekError(f"无法从 URL 解析主机: {url}")
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise DeepSeekError(
            f"DNS 失败 {host}: {exc}\n{VPN_HINT}",
            vpn_likely=True,
        ) from exc


def post_chat(
    url: str,
    api_key: str,
    payload: dict,
    timeout: int = 180,
    extra_headers: dict[str, str] | None = None,
) -> dict:
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
            return json.loads(err_text) if err_text else {"error": {"message": f"HTTP {exc.code}"}}
        except json.JSONDecodeError:
            raise DeepSeekError(f"HTTP {exc.code}: {err_text[:400]}") from exc
    except urllib.error.URLError as exc:
        raise DeepSeekError(f"连接失败: {exc.reason}\n{VPN_HINT}", vpn_likely=True) from exc
    except TimeoutError as exc:
        raise DeepSeekError(f"超时（{timeout}s）。可把 DEEPSEEK_ENABLE_THINKING=false 再试。") from exc
