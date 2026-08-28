# AI Agent

当前产品是 **大气环境诊断助手**，代码在 [aq-assistant/](aq-assistant/)。

运行时内核（`run_loop` / ToolBus）在 [proto/src/agentos/](proto/src/agentos/)，由 `aq-assistant` 通过 `PYTHONPATH` 引用。

DeepSeek 网关配置在本目录 `.env`；连通性脚本：`test_deepseek_api.py`、`setup_ds_hosts.ps1`。

从这里开始：[aq-assistant/README.md](aq-assistant/README.md)
