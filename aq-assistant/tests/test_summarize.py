from agentos.runtime.models import EventType, RunStatus
from agentos.tools.bus import ToolBus
from agentos.tools.echo import EchoTool

from aqagent.constants import ANALYZER_IDS
from aqagent.gateway.deepseek import DeepSeekError, SUMMARIZE_SYSTEM, analysis_evidence
from aqagent.runtime import run_aq
from aqagent.tools.ask import AskUserTool
from aqagent.tools.list_analyzers import ListAnalyzersTool
from aqagent.tools.load_episode import LoadEpisodeTool
from aqagent.tools.run_analysis import RunAnalysisTool

import json


def _fake_bus():
    def runner(**kwargs):
        ids = kwargs["analyzers"]
        return {
            "ok": True,
            "analyzers_run": ids,
            "analyzer_count": len(ids),
            "full_suite": ids == ANALYZER_IDS,
            "primary_source": "public",
            "summaries": {ids[0]: {"seesaw_status": "有效（负相关主导）"} if ids else {}},
            "warnings": [],
            "output_dir": "/tmp/fake",
        }

    return ToolBus(
        tools=[
            EchoTool(),
            ListAnalyzersTool(),
            AskUserTool(),
            LoadEpisodeTool(),
            RunAnalysisTool(runner=runner),
        ]
    )


def _last_yield(run):
    for ev in reversed(run.events):
        if ev.type == EventType.yield_:
            return ev
    return None


def test_llm_summary_replaces_final_message():
    run = run_aq(
        "分析南昌 2026-03-10 到 2026-03-20 的跷跷板",
        tools=_fake_bus(),
        llm_summarize=True,
        summarizer=lambda goal, payload: "核心结论：跷跷板有效。",
    )
    assert run.status == RunStatus.completed
    names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
    assert names == ["run_analysis"]
    last = _last_yield(run)
    assert last is not None
    assert last.payload.get("source") == "deepseek"
    assert last.payload["message"] == "核心结论：跷跷板有效。"


def test_llm_failure_keeps_rules_message():
    def boom(goal, payload):
        raise DeepSeekError("vpn down")

    run = run_aq(
        "分析南昌 2026-03-10 到 2026-03-20 的跷跷板",
        tools=_fake_bus(),
        llm_summarize=True,
        summarizer=boom,
    )
    assert run.status == RunStatus.completed
    last = _last_yield(run)
    assert last is not None
    assert last.payload.get("source") != "deepseek"
    assert "seesaw_effect" in last.payload["message"]
    reasons = [e.payload.get("reason") for e in run.events if e.type == EventType.error]
    assert "summarize_failed" in reasons


def test_list_intent_does_not_summarize():
    called = {"n": 0}

    def spy(goal, payload):
        called["n"] += 1
        return "should not run"

    run = run_aq("有哪些分析器", llm_summarize=True, summarizer=spy)
    assert called["n"] == 0
    last = _last_yield(run)
    assert last is not None
    assert "seesaw_effect" in last.payload["message"]


def test_evidence_omits_empty_and_keeps_summaries():
    ev = analysis_evidence(
        "goal",
        {
            "analyzers_run": ["seesaw_effect"],
            "warnings": [],
            "summaries": {"seesaw_effect": {"seesaw_status": "有效"}},
            "report_excerpt": "should not be copied wholesale",
        },
    )
    assert ev["result"]["analyzers_run"] == ["seesaw_effect"]
    assert "warnings" not in ev["result"]
    assert "report_excerpt" not in ev["result"]
    assert ev["result"]["summaries"]["seesaw_effect"]["seesaw_status"] == "有效"
    assert ev["not_given"] == "无"
    assert ev["analyzer_catalog"][0]["id"] == "seesaw_effect"
    assert "PM2.5" in ev["analyzer_catalog"][0]["name"]
    assert "forbidden_unless_in_json" not in ev
    blob = json.dumps(ev, ensure_ascii=False)
    assert "VOCs" not in blob


def test_not_given_when_summary_empty():
    ev = analysis_evidence(
        "goal",
        {
            "analyzers_run": ["seesaw_effect", "transport_capacity"],
            "summaries": {"seesaw_effect": {"seesaw_status": "有效"}, "transport_capacity": {}},
        },
    )
    assert ev["not_given"] == "transport_capacity 无有效结果"


def test_summarize_prompt_forbids_padding():
    assert "本次未给出" in SUMMARIZE_SYSTEM
    assert "management_implication" in SUMMARIZE_SYSTEM
    assert "VOCs" not in SUMMARIZE_SYSTEM
    assert "not_given" in SUMMARIZE_SYSTEM
    assert "例如浓度、气象" not in SUMMARIZE_SYSTEM
