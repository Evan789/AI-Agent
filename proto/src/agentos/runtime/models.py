from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EventType(str, Enum):
    pack = "pack"
    llm = "llm"
    tool_call = "tool_call"
    tool_result = "tool_result"
    yield_ = "yield"
    error = "error"


class RunEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    seq: int
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    t: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Run(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    goal: str
    status: RunStatus = RunStatus.queued
    max_steps: int = 8
    step_count: int = 0
    fail_reason: str | None = None
    cancel_requested: bool = False
    events: list[RunEvent] = Field(default_factory=list)

    def add(self, type: EventType, payload: dict[str, Any] | None = None) -> RunEvent:
        ev = RunEvent(run_id=self.id, seq=len(self.events), type=type, payload=payload or {})
        self.events.append(ev)
        return ev
