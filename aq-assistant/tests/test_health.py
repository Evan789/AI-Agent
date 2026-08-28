from aqagent.health import health_payload
from aqagent.tools.schema import STAGE_TOOL_NAMES, TOOL_SCHEMAS


def test_health_no_gpu_and_vpn_flag():
    h = health_payload()
    assert h["ok"] is True
    assert h["gpu_required"] is False
    assert h["path"] == "B"
    assert h["vpn_required_for_llm"] is True
    assert h["backend_default"] == "rules"


def test_schema_includes_run_analysis():
    assert "run_analysis" in STAGE_TOOL_NAMES
    assert "run_analysis" in TOOL_SCHEMAS
    assert set(TOOL_SCHEMAS) >= set(STAGE_TOOL_NAMES)
