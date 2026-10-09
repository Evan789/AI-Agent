"""Local chat shell. Same loop as `aqagent ask`; does not reimplement analyzers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from aqagent.config import Settings
from aqagent.constants import ANALYZERS
from aqagent.health import health_payload
from aqagent.planner.slots import parse_skill_flag
from aqagent.runtime import ask_result, run_aq
from aqagent.tools.run_analysis import resolve_figure

STATIC_DIR = Path(__file__).resolve().parent / "static"


class AskBody(BaseModel):
    goal: str = Field(min_length=1)
    llm: bool = True
    skill: str | None = None


def create_app(*, ask_fn: Callable[..., dict] | None = None, settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings()

    def _ask(goal: str, llm: bool, analyzers: list[str] | None) -> dict:
        if ask_fn is not None:
            return ask_fn(goal, llm, analyzers)
        run = run_aq(goal, llm_summarize=llm, persist=True, analyzers=analyzers)
        return ask_result(run)

    app = FastAPI(title="大气环境诊断助手", version="0.1.0")

    @app.get("/api/health")
    def health():
        return health_payload()

    @app.get("/api/analyzers")
    def analyzers():
        return {"analyzers": ANALYZERS, "count": len(ANALYZERS)}

    @app.post("/api/ask")
    def ask(body: AskBody):
        return _ask(body.goal.strip(), body.llm, parse_skill_flag(body.skill))

    @app.get("/api/jobs/{job_id}/figures/{name}")
    def figure(job_id: str, name: str):
        path = resolve_figure(cfg.work_dir, job_id, name)
        if path is None:
            raise HTTPException(status_code=404, detail="找不到该图表")
        return FileResponse(path, media_type="image/png")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
