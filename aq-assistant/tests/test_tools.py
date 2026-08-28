from aqagent.tools.bus import aq_bus
from aqagent.tools.list_analyzers import ListAnalyzersTool
from aqagent.tools.schema import STAGE_TOOL_NAMES, TOOL_SCHEMAS


def test_list_analyzers_count():
    out = ListAnalyzersTool().run({})
    assert out["ok"] is True
    assert out["count"] == 11
    ids = [a["id"] for a in out["analyzers"]]
    assert "seesaw_effect" in ids
    assert "situation_assessment" in ids


def test_bus_unknown_tool():
    bus = aq_bus()
    out = bus.dispatch("not_a_tool", {})
    assert out["ok"] is False
    assert "unknown_tool" in out["error"]


def test_stage_tool_names_match_schema():
    bus = aq_bus()
    for name in STAGE_TOOL_NAMES:
        assert name in bus.names
        assert name in TOOL_SCHEMAS
    assert "load_episode" in bus.names
