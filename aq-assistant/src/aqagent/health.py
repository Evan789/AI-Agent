from aqagent.config import Settings
from aqagent.gateway.rules import AqRulesGateway


def health_payload(settings: Settings | None = None) -> dict:
    cfg = settings or Settings()
    rules = AqRulesGateway("").health()
    return {
        "ok": True,
        "vertical": "air_quality",
        "path": "B",
        "backend_default": "rules",
        "llm_configured": cfg.llm_configured,
        "llm_backend": "deepseek" if cfg.llm_configured else None,
        "vpn_required_for_llm": True,
        "vpn_hint": "调用 DeepSeek 需在既定 VPN 下访问 ds.local.ai",
        "skill_dir": str(cfg.skill_dir),
        "skill_exists": cfg.skill_exists,
        "gpu_required": False,
        "rules": rules,
    }
