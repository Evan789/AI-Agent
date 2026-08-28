# 已锁定决策 · 大气环境诊断助手

- 日期：2026-08-28
- 状态：已确认（路径 B）
- 代码：`AI Agent/aq-assistant/`
- 分析引擎：继续用 `Desktop/aq-assistant-pro/skill/air-quality-analysis`（子进程，阶段 2 接入）

---

## D-AQ1. 产品在 aq-assistant，运行时内核在 proto

`aq-assistant/` 是大气环境诊断助手。`proto/src/agentos/` 只保留循环内核（`run_loop` / ToolBus / Decision），不再是研究助手产品。

## D-AQ2. 大模型 = 内网 DeepSeek v4 网关

- 配置：仓库根 `AI Agent/.env`（`DEEPSEEK_API_URL` / `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL_ID`）
- 协议：与 `test_deepseek_api.py` 相同（compatible-mode，Bearer AppKey，`code==0`）
- **必须在既定 VPN 下调用**。DNS/`ds.local.ai` 失败视为环境问题，不是业务 bug
- Agent 循环默认 `DEEPSEEK_ENABLE_THINKING=false`（要稳定 JSON Decision）
- 业务代码只认 Gateway；禁止分析器里调 LLM

## D-AQ3. 模型不直接碰世界

副作用只走 ToolBus。阶段 1 工具：`echo` / `list_analyzers` / `ask_user`。  
阶段 2 再加 `run_analysis`（现有 `main.py` 子进程）。

## D-AQ4. 默认 Rules，DeepSeek 可插

无 VPN / 未配置时：`python -m aqagent ask` 走规则网关，评测必须绿。  
`--llm` 才打 DeepSeek。

## D-AQ5. 每模块单测

合入前 `pytest tests/ -q`。Live 探测单独：`python -m aqagent probe`。
