from typing import Any

from aqagent.constants import ANALYZERS
from aqagent.config import Settings


class ListAnalyzersTool:
    name = "list_analyzers"

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        settings = Settings()
        return {
            "ok": True,
            "analyzers": ANALYZERS,
            "count": len(ANALYZERS),
            "skill_dir": str(settings.skill_dir),
            "skill_exists": settings.skill_exists,
        }
