from typing import Any


class AskUserTool:
    name = "ask_user"

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "clarify": str(args.get("question") or "")}
