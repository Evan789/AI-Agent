"""Local window. Serves the page and the same agent loop."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from yxbot.config import PACKAGE_ROOT, load_settings, save_settings
from yxbot.gateway import DeepSeekGateway, GatewayError
from yxbot.loop import Agent, AgentError

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ChatBody(BaseModel):
    message: str = Field(min_length=1)


class ConfirmBody(BaseModel):
    allow: bool


class WorkspaceBody(BaseModel):
    path: str = Field(min_length=1)


class SettingsBody(BaseModel):
    api_url: str = ""
    model_id: str = ""
    api_key: str = ""
    host_ip: str = ""


def create_app(agent: Agent | None = None) -> FastAPI:
    settings = load_settings()
    default_workspace = (PACKAGE_ROOT / "workspace").resolve()
    if settings.workspace.resolve() == default_workspace:
        default_workspace.mkdir(parents=True, exist_ok=True)
        settings.workspace = default_workspace
    bot = agent or Agent(DeepSeekGateway(settings), settings.workspace)
    held = {"settings": settings, "agent": bot}

    app = FastAPI(title="YXBot", version="0.1.0")

    def _state() -> dict:
        data = held["agent"].state()
        data["configured"] = held["settings"].configured
        return data

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    def state():
        return _state()

    @app.post("/api/chat")
    def chat(body: ChatBody):
        try:
            held["agent"].user_say(body.message)
        except AgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _state()

    @app.post("/api/confirm")
    def confirm(body: ConfirmBody):
        try:
            held["agent"].confirm(body.allow)
        except AgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _state()

    @app.post("/api/workspace")
    def workspace(body: WorkspaceBody):
        try:
            held["agent"].set_workspace(Path(body.path))
        except AgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        held["settings"].workspace = held["agent"].workspace
        save_settings(held["settings"])
        return _state()

    @app.post("/api/reset")
    def reset():
        held["agent"].reset()
        return _state()

    @app.get("/api/settings")
    def get_settings():
        cfg = held["settings"]
        return {
            "api_url": cfg.api_url,
            "model_id": cfg.model_id,
            "host_ip": cfg.host_ip,
            "key_set": bool(cfg.api_key),
        }

    @app.post("/api/settings")
    def put_settings(body: SettingsBody):
        cfg = held["settings"]
        if body.api_url.strip():
            cfg.api_url = body.api_url.strip()
        if body.model_id.strip():
            cfg.model_id = body.model_id.strip()
        cfg.host_ip = body.host_ip.strip()
        new_key = body.api_key.strip() or None
        if new_key:
            cfg.api_key = new_key
        save_settings(cfg, api_key=new_key)
        held["agent"].gateway = DeepSeekGateway(cfg)
        return {"ok": True, "key_set": bool(cfg.api_key)}

    @app.post("/api/test")
    def test_gateway():
        gateway = DeepSeekGateway(held["settings"])
        try:
            turn = gateway.complete(
                [
                    {"role": "system", "content": "只回复 ok"},
                    {"role": "user", "content": "ping"},
                ],
                None,
            )
        except GatewayError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"ok": True, "reply": (turn.content or "")[:80]}

    return app
