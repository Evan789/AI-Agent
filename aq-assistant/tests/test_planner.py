from aqagent.constants import ANALYZER_IDS
from aqagent.planner.slots import normalize_analyzer_ids, parse_skill_flag, parse_slots, select_analyzers


def test_list_intent():
    s = parse_slots("有哪些分析器")
    assert s["intent"] == "list"
    assert s["city"] is None


def test_analyze_city_dates():
    s = parse_slots("分析南昌 2026-03-10 到 2026-03-20 的 PM2.5 污染过程")
    assert s["intent"] == "analyze"
    assert s["city"] == "南昌"
    assert s["start"] == "2026-03-10"
    assert s["end"] == "2026-03-20"
    assert s["analyzers"] == ANALYZER_IDS


def test_seesaw_maps_to_one_analyzer():
    assert select_analyzers("只看跷跷板") == ["seesaw_effect"]
    s = parse_slots("这次过程有没有跷跷板")
    assert s["intent"] == "analyze"
    assert s["analyzers"] == ["seesaw_effect"]


def test_two_analyzers_by_name_and_id():
    s = parse_slots("南昌做形势研判和 seesaw_effect")
    assert "situation_assessment" in s["analyzers"]
    assert "seesaw_effect" in s["analyzers"]
    assert len(s["analyzers"]) == 2


def test_missing_city():
    s = parse_slots("帮我诊断这次污染过程")
    assert s["intent"] == "analyze"
    assert s["city"] is None


def test_normalize_rejects_unknown():
    ids, err = normalize_analyzer_ids(["seesaw_effect", "not_a_thing"])
    assert ids == []
    assert err is not None
    assert "not_a_thing" in err


def test_parse_skill_flag():
    assert parse_skill_flag("all") == ANALYZER_IDS
    assert parse_skill_flag("seesaw_effect,blh_coupling") == ["seesaw_effect", "blh_coupling"]
    assert parse_skill_flag(None) is None


def test_followup_flag():
    s = parse_slots("那输送呢")
    assert s["followup"] is True
    assert s["analyzers"] == ["transport_capacity"]
    assert s["city"] is None
