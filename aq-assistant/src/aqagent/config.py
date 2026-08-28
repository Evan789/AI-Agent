"""Paths and DeepSeek settings. Secrets live in AI Agent/.env — never commit them."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
AI_AGENT_ROOT = PACKAGE_ROOT.parent
DEFAULT_SKILL_DIR = Path(r"C:\Users\Evan\Desktop\aq-assistant-pro\skill\air-quality-analysis")


def load_dotenv() -> None:
    for path in (AI_AGENT_ROOT / ".env", PACKAGE_ROOT / ".env"):
        if not path.exists():
            continue
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


class Settings:
    def __init__(self) -> None:
        load_dotenv()
        skill = _env("AQA_SKILL_DIR")
        self.skill_dir = Path(skill) if skill else DEFAULT_SKILL_DIR
        self.deepseek_api_key = _env("DEEPSEEK_API_KEY")
        self.deepseek_api_url = _env("DEEPSEEK_API_URL")
        self.deepseek_model_id = _env("DEEPSEEK_MODEL_ID")
        self.deepseek_host_ip = _env("DEEPSEEK_HOST_IP")
        thinking = _env("DEEPSEEK_ENABLE_THINKING", "false")
        self.deepseek_enable_thinking = thinking.lower() in {"1", "true", "yes", "on"}
        self.deepseek_timeout_sec = int(_env("DEEPSEEK_TIMEOUT_SEC", "180") or "180")
        work = _env("AQA_WORK_DIR")
        self.work_dir = Path(work) if work else PACKAGE_ROOT / "work"
        py = _env("AQA_PYTHON")
        self.python = Path(py) if py else Path(sys.executable)
        self.job_timeout_sec = int(_env("AQA_JOB_TIMEOUT_SEC", "300") or "300")

    @property
    def llm_configured(self) -> bool:
        return bool(self.deepseek_api_key and self.deepseek_api_url and self.deepseek_model_id)

    @property
    def skill_exists(self) -> bool:
        return (self.skill_dir / "scripts" / "main.py").is_file()
