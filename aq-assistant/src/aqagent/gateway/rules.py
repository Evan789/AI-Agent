"""Deterministic AQ policy. No weights."""

from __future__ import annotations

import json
from typing import Any, Literal

from agentos.gateway.base import Decision, DecisionKind, GenerateResponse

from aqagent.constants import ANALYZER_IDS
from aqagent.planner.slots import is_subset_pick, parse_slots
from aqagent.session import Episode
from aqagent.tools.run_analysis import collect_figures


_MISSING_Q = "请补充城市（或上传监测文件）以及分析起止日期（YYYY-MM-DD）。离线模式必须先上传文件。"


def apply_episode(slots: dict, ep: Episode | None) -> dict:
    if ep is None:
        return slots
    intent = slots.get("intent")
    if intent == "plot":
        if slots.get("city") and slots.get("city") != ep.city:
            return slots
        out = dict(slots)
        out["city"] = out.get("city") or ep.city
        out["start"] = out.get("start") or ep.start
        out["end"] = out.get("end") or ep.end
        out["reused_episode"] = True
        out["reuse_dirs"] = ep.output_dirs()
        out["known_analyzers"] = list(ep.analyzers_run)
        return out
    if slots.get("city"):
        return slots
    if intent != "analyze":
        return slots
    reuse = is_subset_pick(slots.get("analyzers") or []) or bool(slots.get("followup"))
    if not reuse:
        return slots
    out = dict(slots)
    out["city"] = ep.city
    out["start"] = out.get("start") or ep.start
    out["end"] = out.get("end") or ep.end
    out["reused_episode"] = True
    out["reuse_dirs"] = ep.output_dirs()
    out["known_analyzers"] = list(ep.analyzers_run)
    return out


class AqRulesGateway:
    def __init__(
        self,
        goal: str = "",
        analyzers_override: list[str] | None = None,
        episode: Episode | None = None,
    ):
        self.goal = goal
        self.episode = episode
        self.slots = apply_episode(parse_slots(goal), episode)
        if analyzers_override is not None:
            self.slots["analyzers"] = list(analyzers_override)
            if episode and not self.slots.get("city"):
                self.slots = apply_episode(self.slots, episode)
        self._last: dict[str, Any] | None = None
        self._acted = False

    def health(self) -> dict:
        return {
            "ok": True,
            "backend": "rules",
            "gpu_required": False,
            "vertical": "air_quality",
            "offline_mode": True,
            "loaded": [],
        }

    def observe(self, result: dict[str, Any]) -> None:
        self._last = result

    def generate(
        self,
        role: Literal["chat", "extract", "embed", "caption", "asr"],
        prompt: str = "",
    ) -> GenerateResponse:
        _ = role, prompt
        return GenerateResponse(model_id="rules", decision=self._next(), text=prompt)

    def _selected(self) -> list[str]:
        picked = self.slots.get("analyzers") or []
        if picked:
            return picked
        if self.slots.get("intent") == "plot":
            dirs = self.slots.get("reuse_dirs") or []
            if dirs and collect_figures(dirs):
                return []
            return ["situation_assessment"]
        if self.slots.get("reused_episode"):
            return []
        return list(ANALYZER_IDS)

    def _next(self) -> Decision:
        intent = self.slots["intent"]
        if intent == "list":
            if not self._acted:
                self._acted = True
                return Decision(
                    kind=DecisionKind.tool_call,
                    thought="user asked for method list",
                    name="list_analyzers",
                    args={},
                )
            items = (self._last or {}).get("analyzers") or []
            lines = [f"- `{a['id']}` {a['name']}：{a['desc']}" for a in items]
            msg = "当前可用分析器：\n" + "\n".join(lines) if lines else "未取得分析器清单。"
            return Decision(kind=DecisionKind.final, thought="list done", message=msg)

        if intent in ("analyze", "plot"):
            if not self.slots["city"] and not self.slots.get("session_file"):
                if not self._acted:
                    self._acted = True
                    return Decision(
                        kind=DecisionKind.tool_call,
                        thought="missing city/file",
                        name="ask_user",
                        args={"question": _MISSING_Q},
                    )
                return Decision(
                    kind=DecisionKind.final,
                    thought="clarify",
                    message=(self._last or {}).get("clarify") or _MISSING_Q,
                )
            if not self._acted:
                self._acted = True
                selected = self._selected()
                reuse_dirs = self.slots.get("reuse_dirs") or []
                if not selected:
                    return Decision(
                        kind=DecisionKind.tool_call,
                        thought="recap last episode",
                        name="load_episode",
                        args={
                            "reuse_dirs": reuse_dirs,
                            "analyzers": self.slots.get("known_analyzers") or [],
                        },
                    )
                args = {
                    "city": self.slots["city"],
                    "start": self.slots["start"],
                    "end": self.slots["end"],
                    "analyzers": selected,
                }
                if reuse_dirs:
                    args["reuse_dirs"] = reuse_dirs
                return Decision(
                    kind=DecisionKind.tool_call,
                    thought=f"run {len(selected)} analyzer(s)",
                    name="run_analysis",
                    args=args,
                )
            return Decision(kind=DecisionKind.final, thought="analysis done", message=self._format_result())

        return Decision(
            kind=DecisionKind.final,
            thought="help",
            message="可以说「有哪些分析器」，「分析南昌 … 的跷跷板」，或追问「那输送呢」。",
        )

    def _format_result(self) -> str:
        last = self._last or {}
        if not last.get("ok"):
            return str(last.get("error") or "分析失败")
        ids = last.get("analyzers_run") or []
        n = last.get("analyzer_count") or len(ids)
        suite = "全量 11 个" if last.get("full_suite") else f"指定 {n} 个（非全量）"
        reused = last.get("reused_analyzers") or []
        ran_now = last.get("ran_now")
        lines = [
            f"已运行：{suite}",
            f"分析器：{', '.join(ids)}",
            f"城市：{self.slots.get('city') or '—'}  时段：{self.slots.get('start') or '—'} ~ {self.slots.get('end') or '—'}",
            f"数据来源：{last.get('primary_source') or '—'}",
        ]
        if last.get("reused") or reused:
            lines.append(f"复用上次结果：{', '.join(reused) or '是'}")
        if ran_now:
            lines.append(f"新计算：{', '.join(ran_now)}")
        warnings = last.get("warnings") or []
        for w in warnings:
            lines.append(f"⚠️ {w}")
        summaries = last.get("summaries") or {}
        for aid, body in summaries.items():
            if not body:
                continue
            lines.append(f"- {aid}: {json.dumps(body, ensure_ascii=False)[:400]}")
        if last.get("output_dir"):
            lines.append(f"产物目录：{last['output_dir']}")
        figs = last.get("figures") or []
        if figs:
            names = [f.get("name") if isinstance(f, dict) else str(f) for f in figs]
            lines.append(f"图表：{len(figs)} 张（{', '.join(names[:6])}）")
        return "\n".join(lines)
