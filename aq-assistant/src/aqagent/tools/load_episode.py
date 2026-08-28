from typing import Any
from pathlib import Path

from aqagent.tools.run_analysis import cached_only_result, load_cached


def discover_result_ids(reuse_dirs) -> list[str]:
    ids: list[str] = []
    for d in reuse_dirs or []:
        rd = Path(d) / "results"
        if not rd.is_dir():
            continue
        for f in sorted(rd.glob("*.json")):
            if f.stem not in ids:
                ids.append(f.stem)
    return ids


class LoadEpisodeTool:
    name = "load_episode"

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        dirs = args.get("reuse_dirs") or []
        ids = list(args.get("analyzers") or []) or discover_result_ids(dirs)
        if not ids:
            return {"ok": False, "error": "没有上次分析可追问。请先完成一次带城市和时段的分析。"}
        cached, _missing = load_cached(ids, dirs)
        if not cached:
            return {"ok": False, "error": "上次产物目录里没有结果文件。"}
        out = cached_only_result(list(cached), cached, dirs)
        out["analyzers_run"] = list(cached)
        return out
