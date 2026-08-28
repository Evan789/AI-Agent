from pathlib import Path

import yaml
from agentos.runtime.models import EventType
from agentos.tools.bus import ToolBus
from agentos.tools.echo import EchoTool

from aqagent.constants import ANALYZER_IDS
from aqagent.runtime import run_aq
from aqagent.tools.ask import AskUserTool
from aqagent.tools.list_analyzers import ListAnalyzersTool
from aqagent.tools.load_episode import LoadEpisodeTool
from aqagent.tools.run_analysis import RunAnalysisTool

CASES = Path(__file__).resolve().parents[1] / "eval" / "cases.yaml"


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
            "summaries": {},
            "warnings": [],
            "output_dir": "/tmp/fake",
        }


def test_eval_cases_yaml():
    doc = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    assert doc["backend"] == "rules"
    for case in doc["cases"]:
        fake = _FakeRun()
        tools = None
        if case.get("dry_run"):
            tools = ToolBus(
                tools=[
                    EchoTool(),
                    ListAnalyzersTool(),
                    AskUserTool(),
                    LoadEpisodeTool(),
                    RunAnalysisTool(runner=fake),
                ]
            )
        run = run_aq(
            case["goal"],
            max_steps=int(case.get("max_steps") or doc["max_steps"]),
            tools=tools,
        )
        expect = case["expect"]
        assert run.status.value == expect["status"], case["id"]
        if "fail_reason" in expect:
            assert run.fail_reason == expect["fail_reason"]
        if "tools" in expect:
            names = [e.payload.get("name") for e in run.events if e.type == EventType.tool_call]
            assert names == expect["tools"], case["id"]
        if "message_contains" in expect:
            texts = [str(e.payload.get("message") or "") for e in run.events if e.type == EventType.yield_]
            blob = "\n".join(texts)
            assert expect["message_contains"] in blob, case["id"]
        if "analyzers" in expect:
            want = ANALYZER_IDS if expect["analyzers"] == "all" else expect["analyzers"]
            assert fake.last is not None, case["id"]
            assert fake.last["analyzers"] == want, case["id"]
