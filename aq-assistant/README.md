# 大气环境诊断助手（路径 B）

第二垂直场景：把 Desktop `aq-assistant-pro` 的 11 个分析器升级为 Agent 工具。  
决策后端默认 **Rules**（可单测、可离线）；云端 **DeepSeek v4** 走已验证的内网网关，**必须在既定 VPN 下调用**。

运行时内核在上级 `proto/src/agentos/`（`run_loop` / ToolBus）。

## 当前阶段：2 + 本地对话页

- 11 个分析器可选择：自然语言（如「跷跷板」「形势研判」或分析器 id），或 `--skill id,id` / `--skill all`
- `run_analysis` 调用 Desktop skill 的 `main.py`，`--skill` 只传选中的 id
- 缺城市会追问；无时段且无本地文件时不启子进程
- 本地对话页 `python -m aqagent serve` 与 CLI 共用 `work/session.json` 和同一套 `run_aq`

```powershell
cd "C:\Users\Evan\Deep Learning\AI Agent\aq-assistant"
$env:PYTHONPATH = "src;..\proto\src"
$env:PYTHONIOENCODING = "utf-8"
python -m pytest -q
python -m aqagent ask "分析南昌 2026-03-10 到 2026-03-20 的跷跷板"
python -m aqagent ask "分析南昌 2026-03-10 到 2026-03-20 的跷跷板" --llm
```

`--llm` 不会让模型选工具：仍由规则选分析器并跑 skill，成功后再把工具 JSON 交给 DeepSeek 写人话摘要（需 VPN）。失败则回退规则原文，`summary_source` 可区分。

同一城市时段会写入 `work/session.json`。之后可追问「那输送呢」（只补跑缺的分析器）或「刚才什么意思」（只读上次结果）。摘要 JSON 不再下发 VOCs/NOx 禁词名单。

## 运行

本包 import `agentos`。用 `PYTHONPATH` 指向 `proto/src`，或先 `pip install -e ../proto`：

```powershell
cd "C:\Users\Evan\Deep Learning\AI Agent\aq-assistant"
python -m pip install -e ".[dev]"
python -m pytest -q
python -m aqagent health
python -m aqagent ask "有哪些分析器"
python -m pip install -e ".[web]"
python -m aqagent serve
```

浏览器打开 `http://127.0.0.1:8765`。对话页默认勾选 DeepSeek 摘要（需 VPN）；与 CLI 追问共用同一会话。

DeepSeek（需 VPN；配置用上级目录已有的 `.env`）：

```powershell
python -m aqagent probe
python -m aqagent ask --llm "有哪些分析器"
```

连通失败时先：连 VPN → `ping ds.local.ai` → 或设 `DEEPSEEK_HOST_IP`。根目录 `setup_ds_hosts.ps1` 可写 hosts。

## 目录

```
aq-assistant/
  src/aqagent/     # 规则网关、DeepSeek、工具、Runtime 包装
  tests/           # 不访问网络
  eval/            # 黄金对话（阶段 0 契约）
  docs/            # 本垂直锁定决策
```
