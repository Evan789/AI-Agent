"""DeepSeek settings. Defaults come from AI Agent/.env. Overrides stay in yxbot.local.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
AI_AGENT_ROOT = PACKAGE_ROOT.parent
LOCAL_SETTINGS = PACKAGE_ROOT / "yxbot.local.json"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    api_key: str
    api_url: str
    model_id: str
    host_ip: str
    workspace: Path
    timeout_sec: int = 120

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_url and self.model_id)


def load_settings() -> Settings:
    load_dotenv(AI_AGENT_ROOT / ".env")
    workspace = PACKAGE_ROOT / "workspace"
    settings = Settings(
        api_key=_env("DEEPSEEK_API_KEY"),
        api_url=_env("DEEPSEEK_API_URL"),
        model_id=_env("DEEPSEEK_MODEL_ID"),
        host_ip=_env("DEEPSEEK_HOST_IP"),
        workspace=workspace,
        timeout_sec=int(_env("DEEPSEEK_TIMEOUT_SEC", "120") or "120"),
    )
    if LOCAL_SETTINGS.exists():
        data = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
        if data.get("api_key"):
            settings.api_key = str(data["api_key"])
        if data.get("api_url"):
            settings.api_url = str(data["api_url"])
        if data.get("model_id"):
            settings.model_id = str(data["model_id"])
        if "host_ip" in data:
            settings.host_ip = str(data.get("host_ip") or "")
        if data.get("workspace"):
            settings.workspace = Path(data["workspace"])
    return settings


def save_settings(settings: Settings, *, api_key: str | None = None) -> None:
    current = {}
    if LOCAL_SETTINGS.exists():
        current = json.loads(LOCAL_SETTINGS.read_text(encoding="utf-8"))
    payload = {
        "api_url": settings.api_url,
        "model_id": settings.model_id,
        "host_ip": settings.host_ip,
        "workspace": str(settings.workspace),
    }
    if api_key:
        payload["api_key"] = api_key
    elif current.get("api_key"):
        payload["api_key"] = current["api_key"]
    LOCAL_SETTINGS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
