from pathlib import Path

from agentos.tools.bus import ToolBus
from agentos.tools.echo import EchoTool

from aqagent.tools.ask import AskUserTool
from aqagent.tools.list_analyzers import ListAnalyzersTool
from aqagent.tools.load_episode import LoadEpisodeTool
from aqagent.tools.run_analysis import RunAnalysisTool


def aq_bus(sandbox_root: Path | None = None, run_analysis: RunAnalysisTool | None = None) -> ToolBus:
    _ = sandbox_root
    return ToolBus(
        tools=[
            EchoTool(),
            ListAnalyzersTool(),
            AskUserTool(),
            LoadEpisodeTool(),
            run_analysis or RunAnalysisTool(),
        ]
    )
