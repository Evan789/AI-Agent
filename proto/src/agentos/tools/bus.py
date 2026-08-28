from typing import Any, Protocol

from agentos.tools.echo import EchoTool


class Tool(Protocol):
    name: str

    def run(self, args: dict[str, Any]) -> dict[str, Any]: ...


class ToolBus:
    def __init__(self, tools: list[Tool] | None = None, authorizer=None):
        self._tools = {t.name: t for t in (tools or [EchoTool()])}
        self.authorizer = authorizer

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.authorizer is not None:
            decision = self.authorizer.authorize(name, args)
            if decision.action != "allow":
                return {"ok": False, "denied": True, "error": decision.reason_code}
        tool = self._tools.get(name)
        if tool is None:
            return {"ok": False, "error": f"unknown_tool:{name}"}
        return tool.run(args)
