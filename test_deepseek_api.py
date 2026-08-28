"""Connectivity probe for the local DeepSeek compatible-mode gateway.

Address 1 (no reasoning_content):  {base}/v1/chat/completions
Address 2 (content + reasoning):   {base}/compatible-mode/v1/chat/completions

This platform is not the public DeepSeek API:
- Auth: Authorization: Bearer <AppKey>
- Thinking switch: enable_thinking (default true)
- Success body: code == 0
- Last messages item must be role=user
- system is only allowed on messages[0]
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
TIMEOUT_SEC = 180
PROMPT = "你是谁？"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def mask(secret: str) -> str:
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing {name}. Copy .env.example to .env and fill it in.")
    return value


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def field(label: str, value) -> None:
    print(f"{label:<22} {value}")


def print_error(data: dict) -> None:
    err = data.get("error") or {}
    print()
    print("=== error (docs: failure body) ===")
    field("error.code", err.get("code"))
    field("error.type", err.get("type"))
    field("error.message", err.get("message"))


def print_success(data: dict) -> None:
    print()
    print("=== top-level (docs: success body) ===")
    field("code", data.get("code"))
    field("id", data.get("id"))
    field("created", data.get("created"))
    created = data.get("created")
    if isinstance(created, (int, float)):
        field("created_local", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created)))
    field("model", data.get("model"))
    field("object", data.get("object"))

    known_top = {"code", "id", "choices", "created", "model", "object", "usage"}
    extra_top = {k: data[k] for k in data if k not in known_top}
    if extra_top:
        print()
        print("=== extra top-level keys (not in docs table) ===")
        print(json.dumps(extra_top, ensure_ascii=False, indent=2))

    usage = data.get("usage") or {}
    print()
    print("=== usage ===")
    field("prompt_tokens", usage.get("prompt_tokens"))
    field("completion_tokens", usage.get("completion_tokens"))
    field("total_tokens", usage.get("total_tokens"))
    extra_usage = {k: usage[k] for k in usage if k not in {"prompt_tokens", "completion_tokens", "total_tokens"}}
    if extra_usage:
        print(json.dumps(extra_usage, ensure_ascii=False, indent=2))

    choices = data.get("choices") or []
    print()
    print(f"=== choices ({len(choices)}) ===")
    for choice in choices:
        print()
        field("index", choice.get("index"))
        field("finish_reason", choice.get("finish_reason"))
        message = choice.get("message") or {}
        field("message.role", message.get("role"))
        extra_msg = {
            k: message[k]
            for k in message
            if k not in {"role", "content", "reasoning_content"}
        }
        if extra_msg:
            print("message extra:")
            print(json.dumps(extra_msg, ensure_ascii=False, indent=2))
        print()
        print("--- message.reasoning_content ---")
        print(message.get("reasoning_content"))
        print()
        print("--- message.content ---")
        print(message.get("content"))
        print("--- end ---")


def print_raw(data: dict) -> None:
    print()
    print("=== raw JSON ===")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def rewrite_url_host(url: str, ip: str) -> tuple[str, str]:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise SystemExit(f"Could not parse host from URL: {url}")
    port = parsed.port
    netloc = f"{ip}:{port}" if port else ip
    rewritten = parsed._replace(netloc=netloc).geturl()
    return rewritten, hostname


def diagnose_host(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        raise SystemExit(f"Could not parse host from URL: {url}")
    print(f"DNS lookup: {host}:{port}")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SystemExit(
            f"DNS failed for {host}: {exc}\n"
            "Windows 11001 means this PC cannot resolve the hostname.\n"
            "This is not an AppKey or model-id problem; the HTTP request was never sent.\n\n"
            "Check in the same PowerShell:\n"
            "  nslookup ds.local.ai\n"
            "  ipconfig /flushdns\n\n"
            "Typical causes:\n"
            "  1. Not on the intranet / VPN that owns ds.local.ai\n"
            "  2. This NIC is using public DNS (8.8.8.8 / 1.1.1.1) instead of corp DNS\n"
            "  3. No hosts entry for ds.local.ai\n\n"
            "If you already know the gateway IP, put it in .env:\n"
            "  DEEPSEEK_HOST_IP=10.x.x.x\n"
            "then rerun. The script will connect to the IP and send Host: ds.local.ai."
        ) from exc
    addrs = sorted({item[4][0] for item in infos})
    print(f"Resolved: {', '.join(addrs)}")


def post_json(
    url: str,
    api_key: str,
    payload: dict,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, str, dict, float]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers=headers,
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            raw = response.read()
            elapsed_ms = (time.perf_counter() - started) * 1000
            return response.status, response.headers.get("Content-Type", ""), json.loads(raw.decode("utf-8")), elapsed_ms
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        err_text = exc.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_text) if err_text else {}
        except json.JSONDecodeError:
            err_json = {"error": {"message": err_text or "(empty error body)", "type": "HTTP_ERROR"}}
        print(f"HTTP {exc.code} after {elapsed_ms:.0f} ms")
        print(json.dumps(err_json, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        raise SystemExit(
            f"Connection failed after {elapsed_ms:.0f} ms: {exc.reason}\n"
            "Typical causes: wrong network, gateway down, or host/port blocked."
        ) from exc
    except TimeoutError as exc:
        raise SystemExit(
            f"Timed out after {TIMEOUT_SEC}s. Thinking is on by default and can be slow."
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Response was not JSON: {exc}") from exc


def main() -> int:
    load_env(ROOT / ".env")
    api_key = require("DEEPSEEK_API_KEY")
    url = require("DEEPSEEK_API_URL")
    model = require("DEEPSEEK_MODEL_ID")
    enable_thinking = env_bool("DEEPSEEK_ENABLE_THINKING", True)
    host_ip = os.environ.get("DEEPSEEK_HOST_IP", "").strip()
    extra_headers: dict[str, str] = {}

    print("DeepSeek gateway connectivity test")
    print(f"URL:              {url}")
    print(f"Model:            {model}")
    print(f"Key:              {mask(api_key)}")
    print(f"enable_thinking:  {enable_thinking}")
    print(f"Timeout:          {TIMEOUT_SEC}s")
    if host_ip:
        url, original_host = rewrite_url_host(url, host_ip)
        extra_headers["Host"] = original_host
        print(f"Connect via IP:   {host_ip}  (Host: {original_host})")
    print()
    if host_ip:
        print(f"Skip DNS; connecting to {host_ip}")
    else:
        diagnose_host(url)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是连通性探针。请简短回答。"},
            {"role": "user", "content": PROMPT},
        ],
        "stream": False,
        "enable_thinking": enable_thinking,
        "max_tokens": 2048,
    }

    print("POST chat/completions ...")
    status, content_type, data, elapsed_ms = post_json(
        url, api_key, payload, extra_headers=extra_headers
    )
    print(f"HTTP {status} in {elapsed_ms:.0f} ms ({content_type})")

    if data.get("error"):
        print_error(data)
        print_raw(data)
        return 1

    code = data.get("code")
    print_success(data)
    print_raw(data)

    if code is not None and code != 0:
        print()
        print("FAIL: docs say code == 0 means success.")
        return 1

    choices = data.get("choices") or []
    if not choices:
        print()
        print("FAIL: no choices.")
        return 1

    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    reasoning = ((choices[0].get("message") or {}).get("reasoning_content") or "").strip()
    if enable_thinking and "compatible-mode" in url and not reasoning:
        print()
        print("Warning: address 2 should return reasoning_content when thinking is on.")

    if not content:
        print()
        print("FAIL: message.content is empty.")
        return 1

    print()
    print("OK: gateway reachable, auth accepted, model returned content.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
