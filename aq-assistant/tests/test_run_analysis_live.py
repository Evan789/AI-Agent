from pathlib import Path
import subprocess

import pytest

from aqagent.config import Settings
from aqagent.tools.run_analysis import RunAnalysisTool


@pytest.mark.skipif(not Settings().skill_exists, reason="air-quality-analysis skill not on disk")
def test_live_one_analyzer_on_sample_csv():
    settings = Settings()
    probe = subprocess.run(
        [str(settings.python), "-c", "import pandas, numpy, matplotlib, scipy"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        pytest.skip("current Python missing pandas/matplotlib (run ask inside the CV env)")
    settings = Settings()
    sample = settings.skill_dir / "assets" / "sample_data" / "sample_hourly_data.csv"
    if not sample.is_file():
        pytest.skip("sample csv missing")
    out = RunAnalysisTool(settings).run(
        {
            "analyzers": ["situation_assessment"],
            "city": "南昌",
            "data": str(sample),
            "no_public": True,
        }
    )
    assert out["ok"] is True, out.get("error")
    assert out["analyzers_run"] == ["situation_assessment"]
    assert out["full_suite"] is False
    assert "situation_assessment.json" in (out.get("result_files") or [])
    assert Path(out["output_dir"]).is_dir()
