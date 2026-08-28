from agentos.runtime.models import EventType, RunStatus
from agentos.tools.bus import ToolBus
from agentos.tools.echo import EchoTool

from aqagent.constants import ANALYZER_IDS
from aqagent.runtime import run_aq
from aqagent.tools.ask import AskUserTool
from aqagent.tools.list_analyzers import ListAnalyzersTool
from aqagent.tools.load_episode import LoadEpisodeTool
from aqagent.tools.run_analysis import RunAnalysisTool


class _FakeRun:
    def __init__(self):
        self.last = None

    def __call__(self, **kwargs):
        self.last = kwargs
        ids = kwargs["analyzers"]
        return {
            "ok": True,
            "analyzers_run": ids,
            "analyzer_count": len(ids),
            "full_suite": ids == ANALYZER_IDS,
            "primary_source": "default",
            "summaries": {ids[0]: {"summary": "dry"} if ids else {}},
            "warnings": [],
            "output_dir": "/tmp/fake",
        }


def _bus_with_fake():
    fake = _FakeRun()
    bus = ToolBus(
        tools=[
            EchoTool(),
            ListAnalyzersTool(),
            AskUserTool(),
            LoadEpisodeTool(),
            RunAnalysisTool(runner=fake),
        ]
    )
    return bus, fake


def test_list_analyzers_loop():
    run = run_aq("有哪些分析器", max_steps=8)
    assert run.status == RunStatus.completed
    names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
    assert names == ["list_analyzers"]
    yield_ev = [e for e in run.events if e.type == EventType.yield_]
    assert yield_ev
    assert "seesaw_effect" in yield_ev[-1].payload["message"]


def test_max_steps_stops():
    run = run_aq("有哪些分析器", max_steps=1)
    assert run.status == RunStatus.failed
    assert run.fail_reason == "budget"


def test_missing_slots_asks_user():
    run = run_aq("帮我诊断这次污染过程", max_steps=8)
    assert run.status == RunStatus.completed
    names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
    assert names == ["ask_user"]


def test_full_process_calls_all_analyzers_on_fake():
    bus, fake = _bus_with_fake()
    run = run_aq("分析南昌 2026-03-10 到 2026-03-20 的污染过程", tools=bus)
    assert run.status == RunStatus.completed
    names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
    assert names == ["run_analysis"]
    assert fake.last["analyzers"] == ANALYZER_IDS


def test_seesaw_calls_only_one_on_fake():
    bus, fake = _bus_with_fake()
    run = run_aq("分析南昌 2026-03-10 到 2026-03-20 的跷跷板", tools=bus)
    assert run.status == RunStatus.completed
    assert fake.last["analyzers"] == ["seesaw_effect"]
    assert fake.last["analyzers"] != ANALYZER_IDS


def test_ask_result_shape_for_list():
    from aqagent.runtime import ask_result

    run = run_aq("有哪些分析器")
    out = ask_result(run)
    assert out["status"] == "completed"
    assert out["tools"] == ["list_analyzers"]
    assert "seesaw_effect" in out["message"]
    assert out["summary_source"] == "rules"
    assert out["analyzers_run"] is None
