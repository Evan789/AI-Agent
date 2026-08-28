from typing import Any, Protocol


class Tool(Protocol):
    name: str

    def run(self, args: dict[str, Any]) -> dict[str, Any]: ...


class EchoTool:
    name = "echo"

    def run(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "echo": str(args.get("text", ""))}
