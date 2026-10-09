from pathlib import Path

from agentos.runtime.models import EventType, RunStatus
from agentos.tools.bus import ToolBus
from agentos.tools.echo import EchoTool

from aqagent.gateway.rules import AqRulesGateway
from aqagent.runtime import run_aq
from aqagent.session import Episode
from aqagent.tools.ask import AskUserTool
from aqagent.tools.list_analyzers import ListAnalyzersTool
from aqagent.tools.load_episode import LoadEpisodeTool
from aqagent.tools.run_analysis import RunAnalysisTool


class _FakeRun:
    def __init__(self):
        self.last = None
        self.calls = 0

    def __call__(self, **kwargs):
        self.last = kwargs
        self.calls += 1
        ids = kwargs["analyzers"]
        return {
            "ok": True,
            "analyzers_run": ids,
            "primary_source": "public",
            "summaries": {i: {"summary": "new"} for i in ids},
            "warnings": [],
            "output_dir": "/tmp/newjob",
        }


def _bus(fake):
    return ToolBus(
        tools=[
            EchoTool(),
            ListAnalyzersTool(),
            AskUserTool(),
            LoadEpisodeTool(),
            RunAnalysisTool(runner=fake),
        ]
    )


def _episode(tmp: Path, analyzers: list[str]) -> Episode:
    results = tmp / "results"
    results.mkdir(parents=True)
    for i in analyzers:
        (results / f"{i}.json").write_text('{"seesaw_status": "有效（负相关主导）"}', encoding="utf-8")
    return Episode(
        city="南昌",
        start="2026-03-10",
        end="2026-03-20",
        analyzers_run=list(analyzers),
        jobs=[{"output_dir": str(tmp), "analyzers_run": list(analyzers)}],
    )


def test_followup_transport_runs_only_missing(tmp_path):
    ep = _episode(tmp_path, ["seesaw_effect"])
    fake = _FakeRun()
    gw = AqRulesGateway("那输送呢", episode=ep)
    d = gw.generate(role="chat").decision
    assert d is not None
    assert d.name == "run_analysis"
    assert d.args["city"] == "南昌"
    assert d.args["analyzers"] == ["transport_capacity"]
    assert d.args["reuse_dirs"] == [str(tmp_path)]
    run = run_aq("那输送呢", tools=_bus(fake), episode=ep)
    assert run.status == RunStatus.completed
    assert fake.calls == 1
    assert fake.last["analyzers"] == ["transport_capacity"]


def test_followup_same_analyzer_does_not_rerun(tmp_path):
    ep = _episode(tmp_path, ["seesaw_effect"])
    fake = _FakeRun()
    run = run_aq("刚才的跷跷板什么意思", tools=_bus(fake), episode=ep)
    assert run.status == RunStatus.completed
    assert fake.calls == 0
    names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
    assert names == ["run_analysis"]
    payload = [e.payload for e in run.events if e.type == EventType.tool_result][-1]
    assert payload.get("reused") is True
    assert payload.get("ran_now") == []


def test_recap_loads_episode(tmp_path):
    ep = _episode(tmp_path, ["seesaw_effect"])
    fake = _FakeRun()
    run = run_aq("刚才什么意思", tools=_bus(fake), episode=ep)
    assert run.status == RunStatus.completed
    names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
    assert names == ["load_episode"]
    assert fake.calls == 0


def test_plot_reuses_episode_figures(tmp_path):
    ep = _episode(tmp_path, ["seesaw_effect"])
    (tmp_path / "results" / "seesaw_effect.png").write_bytes(b"png")
    fake = _FakeRun()
    gw = AqRulesGateway("把刚才的图画出来", episode=ep)
    d = gw.generate(role="chat").decision
    assert d is not None
    assert d.name == "load_episode"
    run = run_aq("把刚才的图画出来", tools=_bus(fake), episode=ep)
    assert fake.calls == 0
    from aqagent.runtime import ask_result
    out = ask_result(run)
    assert out["figures"]
    assert out["figures"][0]["name"] == "seesaw_effect.png"


def test_without_episode_still_asks_city():
    fake = _FakeRun()
    run = run_aq("帮我诊断这次污染过程", tools=_bus(fake))
    names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
    assert names == ["ask_user"]
    assert fake.calls == 0
