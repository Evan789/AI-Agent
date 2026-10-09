import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from aqagent.web import create_app


def test_ask_endpoint_uses_injected_fn():
    def fake(goal, llm, analyzers=None):
        return {
            "status": "completed",
            "steps": 1,
            "message": "ok:" + goal,
            "summary_source": "rules" if not llm else "deepseek",
            "summarize_error": None,
            "fail_reason": None,
            "tools": ["list_analyzers"],
            "analyzers_run": analyzers,
            "reused": None,
            "ran_now": None,
        }

    client = TestClient(create_app(ask_fn=fake))
    res = client.post("/api/ask", json={"goal": "有哪些分析器", "llm": False})
    assert res.status_code == 200
    body = res.json()
    assert body["message"] == "ok:有哪些分析器"
    assert body["summary_source"] == "rules"
    home = client.get("/")
    assert home.status_code == 200
    assert "大气环境诊断助手" in home.text
    assert 'id="skill"' in home.text


def test_figure_route_serves_png(tmp_path):
    from aqagent.config import Settings

    class _Cfg(Settings):
        def __init__(self):
            super().__init__()
            self.work_dir = tmp_path

    results = tmp_path / "jobs" / "job1" / "results"
    results.mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\n"
    (results / "a.png").write_bytes(png)
    client = TestClient(create_app(ask_fn=lambda g, l, a: {}, settings=_Cfg()))
    res = client.get("/api/jobs/job1/figures/a.png")
    assert res.status_code == 200
    assert res.content.startswith(b"\x89PNG")
    missing = client.get("/api/jobs/job1/figures/nope.png")
    assert missing.status_code == 404
    traversal = client.get("/api/jobs/../figures/a.png")
    assert traversal.status_code == 404


def test_ask_skill_override_and_catalog():
    seen = {}

    def fake(goal, llm, analyzers=None):
        seen["analyzers"] = analyzers
        return {
            "status": "completed",
            "steps": 1,
            "message": "ok",
            "summary_source": "rules",
            "summarize_error": None,
            "fail_reason": None,
            "tools": ["run_analysis"],
            "analyzers_run": analyzers,
            "reused": None,
            "ran_now": analyzers,
        }

    client = TestClient(create_app(ask_fn=fake))
    catalog = client.get("/api/analyzers").json()
    assert catalog["count"] == 11
    ids = [a["id"] for a in catalog["analyzers"]]
    assert "seesaw_effect" in ids
    res = client.post(
        "/api/ask",
        json={"goal": "分析南昌 2026-03-10 到 2026-03-20", "llm": False, "skill": "seesaw_effect"},
    )
    assert res.status_code == 200
    assert seen["analyzers"] == ["seesaw_effect"]
    all_res = client.post(
        "/api/ask",
        json={"goal": "分析南昌 2026-03-10 到 2026-03-20", "llm": False, "skill": "all"},
    )
    assert all_res.status_code == 200
    assert seen["analyzers"] is not None
    assert len(seen["analyzers"]) == 11
