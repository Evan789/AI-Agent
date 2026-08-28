from __future__ import annotations

import argparse
import json
import sys

from aqagent.config import Settings
from aqagent.gateway.deepseek import DeepSeekError, DeepSeekGateway, diagnose_host
from aqagent.health import health_payload
from aqagent.planner.slots import parse_skill_flag
from aqagent.runtime import ask_result, run_aq


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    parser = argparse.ArgumentParser(prog="aqagent", description="大气环境诊断助手（路径 B）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="健康检查（不访问外网）")

    ask = sub.add_parser("ask", help="用规则网关跑一轮（默认，不调 DeepSeek）")
    ask.add_argument("goal")
    ask.add_argument(
        "--llm",
        action="store_true",
        help="分析成功后用 DeepSeek 写诊断摘要（选分析器仍走规则；需 VPN）",
    )
    ask.add_argument("--max-steps", type=int, default=8)
    ask.add_argument(
        "--skill",
        default=None,
        help="分析器 id，逗号分隔，或 all。覆盖自然语言选择。例：seesaw_effect 或 seesaw_effect,blh_coupling",
    )

    sub.add_parser("probe", help="探测 DeepSeek 网关（需 VPN）")

    serve = sub.add_parser("serve", help="本地对话页（默认 127.0.0.1:8765）")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    if args.cmd == "health":
        print(json.dumps(health_payload(), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "ask":
        try:
            analyzers = parse_skill_flag(args.skill)
            run = run_aq(
                args.goal,
                max_steps=args.max_steps,
                analyzers=analyzers,
                llm_summarize=bool(args.llm),
                persist=True,
            )
        except DeepSeekError as exc:
            print(f"FAIL: {exc}")
            return 1
        print(json.dumps(ask_result(run), ensure_ascii=False, indent=2))
        return 0 if run.status.value == "completed" else 1
    if args.cmd == "serve":
        try:
            import uvicorn
            from aqagent.web import create_app
        except ImportError:
            print('需要先安装 Web 依赖：python -m pip install -e ".[web]"')
            return 1
        print(f"http://{args.host}:{args.port}")
        uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
        return 0
    if args.cmd == "probe":
        settings = Settings()
        print("DeepSeek probe")
        print(f"url:    {settings.deepseek_api_url or '(missing)'}")
        print(f"model:  {settings.deepseek_model_id or '(missing)'}")
        print(f"key:    {'set' if settings.deepseek_api_key else 'missing'}")
        print("vpn:    required")
        try:
            if not settings.deepseek_host_ip and settings.deepseek_api_url:
                diagnose_host(settings.deepseek_api_url)
            gw = DeepSeekGateway(settings)
            text = gw.complete(
                [
                    {"role": "system", "content": "你是连通性探针。请简短回答。"},
                    {"role": "user", "content": "你是谁？"},
                ]
            )
        except DeepSeekError as exc:
            print(f"FAIL: {exc}")
            return 1
        print("OK:")
        print(text[:500])
        return 0
    return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
