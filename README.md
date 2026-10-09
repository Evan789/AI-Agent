# AI Agent

当前产品是 **大气环境诊断助手**，代码在 [aq-assistant/](aq-assistant/)。

运行时内核（`run_loop` / ToolBus）在 [proto/src/agentos/](proto/src/agentos/)，由 `aq-assistant` 通过 `PYTHONPATH` 引用。

DeepSeek 网关配置在本目录 `.env`；连通性脚本：`test_deepseek_api.py`、`setup_ds_hosts.ps1`。

从这里开始：[aq-assistant/README.md](aq-assistant/README.md)

通用 Agent（自己的界面终端、大陆厂商 API、介绍页下载、账号、自动更新）的构建说明在 [通用AI Agent构建/README.md](通用AI%20Agent构建/README.md)。尚未写代码。
