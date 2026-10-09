from agentos.gateway.base import DecisionKind

from aqagent.constants import ANALYZER_IDS
from aqagent.gateway.rules import AqRulesGateway


def test_list_then_final():
    gw = AqRulesGateway("有哪些分析器")
    d1 = gw.generate(role="chat").decision
    assert d1 is not None
    assert d1.kind == DecisionKind.tool_call
    assert d1.name == "list_analyzers"
    gw.observe({"ok": True, "analyzers": [{"id": "seesaw_effect", "name": "跷跷板", "desc": "x"}]})
    d2 = gw.generate(role="chat").decision
    assert d2 is not None
    assert d2.kind == DecisionKind.final
    assert "seesaw_effect" in d2.message


def test_analyze_missing_city_asks():
    gw = AqRulesGateway("帮我诊断这次污染过程")
    d1 = gw.generate(role="chat").decision
    assert d1 is not None
    assert d1.name == "ask_user"
    gw.observe({"ok": True, "clarify": "请补充城市"})
    d2 = gw.generate(role="chat").decision
    assert d2 is not None
    assert d2.kind == DecisionKind.final
    assert "城市" in d2.message


def test_full_process_selects_all_eleven():
    gw = AqRulesGateway("分析南昌 2026-03-10 到 2026-03-20 的污染过程")
    d = gw.generate(role="chat").decision
    assert d is not None
    assert d.name == "run_analysis"
    assert d.args["city"] == "南昌"
    assert d.args["start"] == "2026-03-10"
    assert d.args["end"] == "2026-03-20"
    assert d.args["analyzers"] == ANALYZER_IDS


def test_seesaw_selects_one():
    gw = AqRulesGateway("分析南昌 2026-03-10 到 2026-03-20 的跷跷板")
    d = gw.generate(role="chat").decision
    assert d is not None
    assert d.name == "run_analysis"
    assert d.args["analyzers"] == ["seesaw_effect"]


def test_override_skill_flag():
    gw = AqRulesGateway(
        "分析南昌 2026-03-10 到 2026-03-20 的污染过程",
        analyzers_override=["blh_coupling"],
    )
    d = gw.generate(role="chat").decision
    assert d is not None
    assert d.args["analyzers"] == ["blh_coupling"]


def test_plot_new_city_runs_situation():
    gw = AqRulesGateway("给我画一个图，展示北京2026-08-01至2026-08-28的空气质量变化趋势")
    d = gw.generate(role="chat").decision
    assert d is not None
    assert d.name == "run_analysis"
    assert d.args["city"] == "北京"
    assert d.args["analyzers"] == ["situation_assessment"]
