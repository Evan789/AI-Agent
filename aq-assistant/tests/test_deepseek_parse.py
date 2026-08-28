from agentos.gateway.base import DecisionKind

from aqagent.gateway.deepseek import parse_decision, rewrite_url_host, VPN_HINT


def test_parse_tool_call_json():
    d = parse_decision('{"kind":"tool_call","name":"list_analyzers","args":{},"thought":"list"}')
    assert d.kind == DecisionKind.tool_call
    assert d.name == "list_analyzers"
    assert d.args == {}


def test_parse_fenced_final():
    d = parse_decision('```json\n{"kind":"final","message":"hello"}\n```')
    assert d.kind == DecisionKind.final
    assert d.message == "hello"


def test_parse_plain_text_as_final():
    d = parse_decision("当前可用 11 个分析器。")
    assert d.kind == DecisionKind.final
    assert "11" in d.message


def test_rewrite_host_keeps_path():
    url, host = rewrite_url_host(
        "http://ds.local.ai:30080/compatible-mode/v1/chat/completions",
        "10.162.6.161",
    )
    assert host == "ds.local.ai"
    assert url.startswith("http://10.162.6.161:30080/")
    assert "compatible-mode" in url


def test_vpn_hint_mentions_ds():
    assert "VPN" in VPN_HINT
    assert "ds.local.ai" in VPN_HINT
