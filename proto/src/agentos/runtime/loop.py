import json

from agentos.context.assemble import assemble
from agentos.gateway.base import DecisionKind, Gateway
from agentos.runtime.models import EventType, Run, RunStatus
from agentos.tools.bus import ToolBus

_OBS_TEXT_CAP = 1500
_EVENT_TEXT_CAP = 2000


def summarize_tool_result(result: dict, cap: int = _OBS_TEXT_CAP) -> dict:
    slim: dict = {}
    for key, val in result.items():
        if isinstance(val, str) and len(val) > cap:
            slim[key] = val[:cap] + "…"
        else:
            slim[key] = val
    return slim


def run_loop(
    run: Run,
    gateway: Gateway,
    tools: ToolBus | None = None,
    char_budget: int = 4000,
    persona: str | None = None,
    policy: str | None = None,
    extra_task_state: str = "",
) -> Run:
    bus = tools or ToolBus()
    run.status = RunStatus.running
    observation = run.goal

    while run.status == RunStatus.running:
        if run.cancel_requested:
            run.status = RunStatus.cancelled
            run.add(EventType.error, {"reason": "cancelled"})
            break
        if run.step_count >= run.max_steps:
            run.status = RunStatus.failed
            run.fail_reason = "budget"
            run.add(EventType.error, {"reason": "budget", "max_steps": run.max_steps})
            break

        assemble_kw = {}
        if persona is not None:
            assemble_kw["persona"] = persona
        if policy is not None:
            assemble_kw["policy"] = policy
        assembled = assemble(
            char_budget=char_budget,
            tool_names=bus.names,
            task_state=extra_task_state,
            observation=observation,
            backend=gateway.health().get("backend", "rules"),
            **assemble_kw,
        )
        run.add(
            EventType.pack,
            {
                "observation": observation[:500],
                "backend": assembled.backend,
                "assembled_used": assembled.used,
            },
        )
        resp = gateway.generate(role="chat", prompt=assembled.text)
        decision = resp.decision
        run.add(EventType.llm, {"model_id": resp.model_id, "decision": decision.model_dump() if decision else {}})
        run.step_count += 1

        if decision is None:
            run.status = RunStatus.failed
            run.fail_reason = "empty_decision"
            break

        if decision.kind == DecisionKind.final:
            run.add(EventType.yield_, {"message": decision.message})
            run.status = RunStatus.completed
            break

        if decision.kind == DecisionKind.tool_call:
            name = decision.name or ""
            run.add(EventType.tool_call, {"name": name, "args": decision.args})
            result = bus.dispatch(name, decision.args)
            run.add(EventType.tool_result, summarize_tool_result(result, cap=_EVENT_TEXT_CAP))
            observe = getattr(gateway, "observe", None)
            if callable(observe):
                observe(result)
            observation = json.dumps(summarize_tool_result(result), ensure_ascii=False, default=str)
            continue

        run.status = RunStatus.failed
        run.fail_reason = f"unsupported_kind:{decision.kind}"
        break

    return run
