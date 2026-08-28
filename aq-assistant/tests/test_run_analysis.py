from aqagent.tools.run_analysis import RunAnalysisTool, _slim


def test_unknown_analyzer_rejected():
    out = RunAnalysisTool(runner=lambda **k: {"ok": True}).run({"analyzers": ["nope"], "city": "南昌", "start": "2026-03-10"})
    assert out["ok"] is False
    assert "未知分析器" in out["error"]


def test_missing_period_without_file():
    out = RunAnalysisTool(runner=lambda **k: {"ok": True}).run(
        {"analyzers": ["seesaw_effect"], "city": "南昌"}
    )
    assert out["ok"] is False
    assert "日期" in out["error"]


def test_runner_receives_subset_and_geo():
    seen = {}

    def runner(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "analyzers_run": kwargs["analyzers"]}

    out = RunAnalysisTool(runner=runner).run(
        {
            "analyzers": ["seesaw_effect", "blh_coupling"],
            "city": "南昌",
            "start": "2026-03-10",
            "end": "2026-03-20",
        }
    )
    assert out["ok"] is True
    assert seen["analyzers"] == ["seesaw_effect", "blh_coupling"]
    assert seen["lat"] == 28.68
    assert seen["lon"] == 115.86


def test_slim_keeps_correlation_fields():
    slim = _slim({
        "seesaw_status": "有效（负相关主导）",
        "mechanism": "x",
        "overall_correlation": {"r": -0.4},
        "sliding_window": {"negative_ratio": 60},
        "noise": 1,
    })
    assert slim["seesaw_status"].startswith("有效")
    assert "overall_correlation" in slim
    assert "sliding_window" in slim
    assert "noise" not in slim


def test_slim_keeps_transport_without_daily_series():
    slim = _slim({
        "ventilation_coefficient": {
            "mean": 4000,
            "capacity_level": "正常",
            "daily": {"2026-03-10": 1, "2026-03-11": 2},
        },
        "cpf": {
            "threshold": 50,
            "dominant_directions": [{"dir": "N", "pct": 20}],
            "cpf_by_dir": {"N": 20, "S": 1},
        },
        "analyzer": "transport_capacity",
    })
    assert slim["ventilation_coefficient"]["capacity_level"] == "正常"
    assert slim["ventilation_coefficient"]["mean"] == 4000
    assert "daily" not in slim["ventilation_coefficient"]
    assert slim["cpf"]["dominant_directions"][0]["dir"] == "N"
    assert "cpf_by_dir" not in slim["cpf"]
    assert "analyzer" not in slim
