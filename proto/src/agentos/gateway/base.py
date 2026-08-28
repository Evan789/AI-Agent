from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class ModelDisabled(Exception):
    def __init__(self, role: str):
        self.role = role
        self.code = "model_disabled"
        super().__init__(f"role={role} is disabled under current vram_profile")


class DecisionKind(str, Enum):
    tool_call = "tool_call"
    final = "final"
    clarify = "clarify"


class Decision(BaseModel):
    kind: DecisionKind
    thought: str = ""
    name: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class GenerateResponse(BaseModel):
    model_id: str
    decision: Decision | None = None
    text: str = ""
    error_code: str | None = None


class Gateway(Protocol):
    def health(self) -> dict[str, Any]: ...

    def generate(
        self,
        role: Literal["chat", "extract", "embed", "caption", "asr"],
        prompt: str = "",
    ) -> GenerateResponse: ...
