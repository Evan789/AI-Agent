"""Run selected analyzers via the air-quality-analysis skill CLI (subprocess)."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable

from aqagent.config import Settings
from aqagent.constants import ANALYZER_IDS
from aqagent.geo import resolve_city
from aqagent.planner.slots import normalize_analyzer_ids

_SUMMARY_KEYS = (
    "summary",
    "pollution_mode",
    "management_implication",
    "mechanism",
    "seesaw_status",
    "overall_correlation",
    "sliding_window",
    "core_findings",
    "conclusion",
    "diagnostics",
    "coupling_state",
    "coupling_correlation",
    "wind_background",
    "arf_assessment",
    "capacity_level",
    "ventilation_coefficient",
    "cpf",
    "stages",
    "change_points",
    "day_night_stats",
    "diurnal_peaks",
    "key_structures",
    "anomalies",
    "pollutants",
    "met_background",
    "phase_pollution_stats",
    "charge_discharge_cycles",
    "insights",
    "terrain_stats",
    "terrain_gradient",
    "breakpoint",
    "r2",
    "critical_threshold",
)

_DROP_NESTED = {
    "ventilation_coefficient": ("daily",),
    "cpf": ("cpf_by_dir",),
}


def _slim(result: dict) -> dict:
    out = {}
    for key in _SUMMARY_KEYS:
        if key not in result:
            continue
        val = result[key]
        drop = _DROP_NESTED.get(key)
        if drop and isinstance(val, dict):
            val = {k: v for k, v in val.items() if k not in drop}
        out[key] = val
    if result.get("error"):
        out["error"] = result["error"]
    return out


def collect_figures(dirs) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in dirs or []:
        if not raw:
            continue
        d = Path(raw)
        results = d / "results" if (d / "results").is_dir() else d
        if not results.is_dir():
            continue
        job_id = d.name
        for f in sorted(results.glob("*.png")):
            if f.name in seen:
                continue
            seen.add(f.name)
            items.append({"job_id": job_id, "name": f.name})
    return items


def resolve_figure(work_dir: Path, job_id: str, name: str) -> Path | None:
    if "/" in job_id or "\\" in job_id or ".." in job_id:
        return None
    if "/" in name or "\\" in name or not name.lower().endswith(".png"):
        return None
    base = (Path(work_dir) / "jobs" / job_id / "results").resolve()
    path = (base / name).resolve()
    if path.parent != base or not path.is_file():
        return None
    return path


class RunAnalysisTool:
    name = "run_analysis"

    def __init__(
        self,
        settings: Settings | None = None,
        runner: Callable[..., dict[str, Any]] | None = None,
    ):
        self.settings = settings or Settings()
        self._runner = runner

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        ids, err = normalize_analyzer_ids(args.get("analyzers") or args.get("skill"))
        if err:
            return {"ok": False, "error": err}
        city = args.get("city")
        start = args.get("start")
        end = args.get("end") or start
        data = args.get("data") or args.get("session_file")
        if not data and (not start or not end):
            return {
                "ok": False,
                "error": "需要起止日期 YYYY-MM-DD，或提供本地数据文件。",
                "analyzers": ids,
            }
        lat = args.get("lat")
        lon = args.get("lon")
        if city and (lat is None or lon is None):
            geo = resolve_city(str(city))
            if geo:
                lat, lon = geo
            elif not data:
                return {"ok": False, "error": f"未识别城市「{city}」的经纬度，请上传数据或改用已知城市。"}
        cached, missing = load_cached(ids, args.get("reuse_dirs"))
        extra_dirs = list(args.get("reuse_dirs") or [])
        if args.get("reuse_dirs") and not missing:
            return cached_only_result(ids, cached, extra_dirs)
        run_ids = missing if args.get("reuse_dirs") else ids
        if self._runner is not None:
            out = self._runner(
                analyzers=run_ids,
                city=city,
                start=start,
                end=end,
                data=data,
                lat=lat,
                lon=lon,
                args=args,
            )
            return _attach_figures(_merge_cached(out, ids, cached, run_ids), extra_dirs)
        exec_out = self._execute(run_ids, city=city, start=start, end=end, data=data, lat=lat, lon=lon, args=args)
        return _attach_figures(_merge_cached(exec_out, ids, cached, run_ids), extra_dirs)

    def _execute(
        self,
        ids: list[str],
        *,
        city,
        start,
        end,
        data,
        lat,
        lon,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.settings.skill_exists:
            return {
                "ok": False,
                "error": f"找不到 skill main.py: {self.settings.skill_dir}",
            }
        job_id = uuid.uuid4().hex[:10]
        out_dir = self.settings.work_dir / "jobs" / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        skill_arg = ",".join(ids)
        main_py = self.settings.skill_dir / "scripts" / "main.py"
        scripts = self.settings.skill_dir / "scripts"
        cmd = [
            str(self.settings.python),
            str(main_py),
            "--skill",
            skill_arg,
            "--output",
            str(out_dir),
        ]
        if data:
            cmd += ["--data", str(data)]
        if city:
            cmd += ["--city", str(city)]
        if lat is not None:
            cmd += ["--lat", str(lat)]
        if lon is not None:
            cmd += ["--lon", str(lon)]
        if start:
            cmd += ["--start", str(start)]
        if end:
            cmd += ["--end", str(end)]
        if args.get("no_public"):
            cmd += ["--no-public"]
        if args.get("no_default"):
            cmd += ["--no-default"]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(scripts),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.settings.job_timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": f"分析超时（{self.settings.job_timeout_sec}s）",
                "job_id": job_id,
                "analyzers_run": ids,
            }

        log = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": log[-2000:] or f"exit {proc.returncode}",
                "job_id": job_id,
                "analyzers_run": ids,
                "cmd_skill": skill_arg,
            }
        return _collect_outputs(out_dir, ids, job_id, skill_arg, log)


def load_cached(ids: list[str], reuse_dirs) -> tuple[dict[str, Any], list[str]]:
    found: dict[str, Any] = {}
    missing: list[str] = []
    dirs = [Path(d) for d in (reuse_dirs or []) if d]
    for i in ids:
        hit = None
        for d in dirs:
            p = d / "results" / f"{i}.json"
            if p.is_file():
                hit = p
                break
        if hit is None:
            missing.append(i)
            continue
        try:
            payload = json.loads(hit.read_text(encoding="utf-8"))
            found[i] = _slim(payload) if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            missing.append(i)
    return found, missing


def cached_only_result(ids: list[str], cached: dict[str, Any], reuse_dirs) -> dict[str, Any]:
    first = Path(reuse_dirs[0]) if reuse_dirs else None
    provenance = {}
    if first is not None and (first / "data_provenance.json").is_file():
        try:
            provenance = json.loads((first / "data_provenance.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            provenance = {}
    return {
        "ok": True,
        "job_id": "reused",
        "reused": True,
        "ran_now": [],
        "reused_analyzers": list(cached),
        "analyzers_run": ids,
        "analyzer_count": len(ids),
        "full_suite": ids == ANALYZER_IDS,
        "cmd_skill": ",".join(ids),
        "output_dir": str(first) if first else "",
        "primary_source": provenance.get("primary_source"),
        "sample_count": provenance.get("sample_count"),
        "warnings": provenance.get("warnings") or [],
        "summaries": cached,
        "result_files": [f"{k}.json" for k in cached],
        "figures": collect_figures(reuse_dirs),
        "report_excerpt": "",
        "log_tail": "",
    }


def _attach_figures(out: dict[str, Any], extra_dirs) -> dict[str, Any]:
    if not out.get("ok"):
        return out
    dirs = []
    if out.get("output_dir"):
        dirs.append(out["output_dir"])
    dirs.extend(extra_dirs or [])
    merged = dict(out)
    merged["figures"] = collect_figures(dirs)
    return merged


def _merge_cached(out: dict[str, Any], requested: list[str], cached: dict[str, Any], ran_now: list[str]) -> dict[str, Any]:
    if not out.get("ok"):
        return out
    summaries = dict(cached)
    summaries.update(out.get("summaries") or {})
    out = dict(out)
    out["summaries"] = summaries
    out["analyzers_run"] = requested
    out["analyzer_count"] = len(requested)
    out["full_suite"] = requested == ANALYZER_IDS
    out["ran_now"] = ran_now
    out["reused_analyzers"] = [i for i in requested if i in cached]
    out["reused"] = bool(cached) and not ran_now
    return out


def _collect_outputs(out_dir: Path, ids: list[str], job_id: str, skill_arg: str, log: str) -> dict[str, Any]:
    provenance = None
    prov_path = out_dir / "data_provenance.json"
    if prov_path.exists():
        try:
            provenance = json.loads(prov_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            provenance = None
    report = ""
    report_path = out_dir / "report.md"
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8")
    results_dir = out_dir / "results"
    slim: dict[str, Any] = {}
    result_files: list[str] = []
    if results_dir.exists():
        for f in sorted(results_dir.iterdir()):
            if f.suffix.lower() == ".json":
                result_files.append(f.name)
                try:
                    payload = json.loads(f.read_text(encoding="utf-8"))
                    slim[f.stem] = _slim(payload) if isinstance(payload, dict) else {}
                except json.JSONDecodeError:
                    slim[f.stem] = {"error": "json_parse_failed"}
    src = (provenance or {}).get("primary_source")
    return {
        "ok": True,
        "job_id": job_id,
        "analyzers_run": ids,
        "analyzer_count": len(ids),
        "full_suite": ids == ANALYZER_IDS,
        "cmd_skill": skill_arg,
        "output_dir": str(out_dir),
        "primary_source": src,
        "sample_count": (provenance or {}).get("sample_count"),
        "warnings": (provenance or {}).get("warnings") or [],
        "summaries": slim,
        "result_files": result_files,
        "figures": collect_figures([out_dir]),
        "report_excerpt": report[:2500],
        "log_tail": log[-800:],
    }
