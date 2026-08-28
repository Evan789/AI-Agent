"""Persist last episode so the next CLI ask can follow up."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from aqagent.config import Settings


@dataclass
class Episode:
    city: str | None = None
    start: str | None = None
    end: str | None = None
    analyzers_run: list[str] = field(default_factory=list)
    jobs: list[dict] = field(default_factory=list)
    goal: str = ""

    def output_dirs(self) -> list[str]:
        return [str(j["output_dir"]) for j in self.jobs if j.get("output_dir")]


def session_path(settings: Settings | None = None) -> Path:
    cfg = settings or Settings()
    return cfg.work_dir / "session.json"


def load_episode(settings: Settings | None = None, path: Path | None = None) -> Episode | None:
    p = path or session_path(settings)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return Episode(
        city=raw.get("city"),
        start=raw.get("start"),
        end=raw.get("end"),
        analyzers_run=list(raw.get("analyzers_run") or []),
        jobs=list(raw.get("jobs") or []),
        goal=str(raw.get("goal") or ""),
    )


def save_episode(ep: Episode, settings: Settings | None = None, path: Path | None = None) -> Path:
    p = path or session_path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(ep), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def record_job(ep: Episode | None, *, city, start, end, goal: str, result: dict) -> Episode:
    """Merge a successful run_analysis result into the episode."""
    same = (
        ep is not None
        and ep.city == city
        and ep.start == start
        and ep.end == end
    )
    out = ep if same else Episode(city=city, start=start, end=end, goal=goal)
    if not same:
        out.analyzers_run = []
        out.jobs = []
    out.goal = goal or out.goal
    ran = list(result.get("analyzers_run") or [])
    for i in ran:
        if i not in out.analyzers_run:
            out.analyzers_run.append(i)
    ran_now = result.get("ran_now")
    if result.get("reused") and not ran_now:
        return out
    job = {
        "job_id": result.get("job_id"),
        "output_dir": result.get("output_dir"),
        "analyzers_run": ran,
        "reused": bool(result.get("reused")),
    }
    if job["output_dir"]:
        out.jobs.append(job)
    return out
