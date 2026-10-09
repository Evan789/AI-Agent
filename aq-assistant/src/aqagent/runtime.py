from agentos.runtime.loop import run_loop
from agentos.runtime.models import EventType, Run, RunStatus

from aqagent.constants import PERSONA, POLICY
from aqagent.gateway.deepseek import DeepSeekError, DeepSeekGateway
from aqagent.gateway.rules import AqRulesGateway
from aqagent.planner.slots import parse_slots
from aqagent.session import Episode, load_episode, record_job, save_episode
from aqagent.tools.bus import aq_bus
from aqagent.tools.run_analysis import collect_figures, load_cached


def ask_result(run: Run) -> dict:
    """CLI / HTTP 共用的一轮回答形状。"""
    final = ""
    summary_source = "rules"
    for ev in reversed(run.events):
        if ev.type == EventType.yield_:
            final = str(ev.payload.get("message") or "")
            summary_source = str(ev.payload.get("source") or "rules")
            break
    summarize_error = None
    for ev in run.events:
        if ev.type == EventType.error and ev.payload.get("reason") == "summarize_failed":
            summarize_error = ev.payload.get("error")
    ran = None
    reused = None
    ran_now = None
    figures = []
    for ev in reversed(run.events):
        if ev.type == EventType.tool_result and isinstance(ev.payload, dict):
            if ev.payload.get("figures"):
                figures = ev.payload.get("figures") or []
            if ev.payload.get("analyzers_run"):
                ran = ev.payload.get("analyzers_run")
                reused = ev.payload.get("reused_analyzers") or ev.payload.get("reused")
                ran_now = ev.payload.get("ran_now")
                if not figures:
                    figures = ev.payload.get("figures") or []
                break
    return {
        "status": run.status.value,
        "steps": run.step_count,
        "message": final,
        "summary_source": summary_source,
        "summarize_error": summarize_error,
        "fail_reason": run.fail_reason,
        "tools": [e.payload.get("name") for e in run.events if e.type == EventType.tool_call],
        "analyzers_run": ran,
        "reused": reused,
        "ran_now": ran_now,
        "figures": figures,
    }


def last_analysis_result(run: Run) -> dict | None:
    for ev in reversed(run.events):
        if ev.type != EventType.tool_result:
            continue
        payload = ev.payload or {}
        if payload.get("ok") and payload.get("analyzers_run"):
            return payload
    return None


def episode_chat_evidence(ep: Episode | None) -> dict:
    if ep is None:
        return {"episode": None}
    cached, _missing = load_cached(ep.analyzers_run or [], ep.output_dirs())
    return {
        "city": ep.city,
        "start": ep.start,
        "end": ep.end,
        "analyzers_run": ep.analyzers_run,
        "summaries": cached,
        "figures": collect_figures(ep.output_dirs()),
    }


def apply_llm_chat(run: Run, goal: str, episode: Episode | None = None, chatter=None) -> Run:
    if run.status != RunStatus.completed:
        return run
    fn = chatter or (lambda g, ev: DeepSeekGateway().chat_about(g, ev))
    try:
        text = (fn(goal, episode_chat_evidence(episode)) or "").strip()
    except DeepSeekError as exc:
        run.add(EventType.error, {"reason": "chat_failed", "error": str(exc)})
        return run
    if not text:
        run.add(EventType.error, {"reason": "chat_empty"})
        return run
    run.add(EventType.yield_, {"message": text, "source": "deepseek"})
    return run


def apply_llm_summary(run: Run, goal: str, summarizer=None) -> Run:
    if run.status != RunStatus.completed:
        return run
    payload = last_analysis_result(run)
    if not payload:
        return run
    fn = summarizer or (lambda g, p: DeepSeekGateway().summarize_analysis(g, p))
    try:
        text = (fn(goal, payload) or "").strip()
    except DeepSeekError as exc:
        run.add(EventType.error, {"reason": "summarize_failed", "error": str(exc)})
        return run
    if not text:
        run.add(EventType.error, {"reason": "summarize_empty"})
        return run
    run.add(EventType.yield_, {"message": text, "source": "deepseek"})
    return run


def run_aq(
    goal: str,
    *,
    gateway=None,
    max_steps: int = 8,
    tools=None,
    analyzers=None,
    llm_summarize: bool = False,
    summarizer=None,
    chatter=None,
    episode: Episode | None = None,
    persist: bool = False,
) -> Run:
    ep = episode
    if persist and ep is None:
        ep = load_episode()
    gw = gateway or AqRulesGateway(goal, analyzers_override=analyzers, episode=ep)
    if analyzers is not None and gateway is None:
        gw.slots["intent"] = "analyze"
        if ep is not None and not gw.slots.get("city"):
            from aqagent.gateway.rules import apply_episode
            gw.slots = apply_episode(gw.slots, ep)
    bus = tools or aq_bus()
    run = Run(goal=goal, max_steps=max_steps)
    run = run_loop(
        run,
        gw,
        tools=bus,
        persona=PERSONA,
        policy=POLICY,
        extra_task_state=f"user_goal={goal}",
    )
    payload = last_analysis_result(run)
    if persist and payload and payload.get("ok"):
        updated = record_job(
            ep,
            city=gw.slots.get("city"),
            start=gw.slots.get("start"),
            end=gw.slots.get("end"),
            goal=goal,
            result=payload,
        )
        save_episode(updated)
    if llm_summarize:
        intent = gw.slots.get("intent") or parse_slots(goal)["intent"]
        if intent == "analyze":
            run = apply_llm_summary(run, goal, summarizer=summarizer)
        elif intent == "chat":
            run = apply_llm_chat(run, goal, episode=ep, chatter=chatter)
    return run
