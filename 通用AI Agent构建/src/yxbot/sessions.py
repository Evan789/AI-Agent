"""Local chat sessions. Files stay on this machine and never store API keys."""

from __future__ import annotations

import json
import uuid
from pathlib import Path


class SessionError(Exception):
    pass


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def _path(self, session_id: str) -> Path:
        if not session_id or any(char in session_id for char in "/\\.") or len(session_id) > 64:
            raise SessionError("会话不存在")
        return self.root / f"{session_id}.json"

    def list_sessions(self) -> list[dict]:
        items = []
        for file in self.root.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            items.append(
                {
                    "id": data.get("id") or file.stem,
                    "title": data.get("title") or "新对话",
                    "updated_at": data.get("updated_at") or "",
                }
            )
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return items

    def latest(self) -> dict | None:
        items = self.list_sessions()
        if not items:
            return None
        return self.load(items[0]["id"])

    def load(self, session_id: str) -> dict:
        file = self._path(session_id)
        if not file.is_file():
            raise SessionError("会话不存在")
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionError("会话无法读取") from exc
        if not isinstance(data, dict):
            raise SessionError("会话无法读取")
        data.pop("api_key", None)
        return data

    def save(self, record: dict) -> None:
        payload = {key: value for key, value in record.items() if key != "api_key"}
        file = self._path(str(payload.get("id") or ""))
        file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete(self, session_id: str) -> None:
        file = self._path(session_id)
        if not file.is_file():
            raise SessionError("会话不存在")
        file.unlink()
