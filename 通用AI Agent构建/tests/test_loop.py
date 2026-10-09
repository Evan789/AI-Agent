import tempfile
import unittest
from pathlib import Path

from yxbot.gateway import ToolCall, Turn
from yxbot.loop import Agent


class ScriptedGateway:
    def __init__(self, turns):
        self.turns = list(turns)

    def complete(self, messages, tools):
        return self.turns.pop(0)


class LoopTests(unittest.TestCase):
    def test_write_waits_for_allow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway = ScriptedGateway(
                [
                    Turn("", [ToolCall("write_file", {"path": "a.txt", "content": "hi"})]),
                    Turn("写好了"),
                ]
            )
            agent = Agent(gateway, root)
            agent.user_say("写个文件")
            self.assertIsNotNone(agent.pending)
            self.assertFalse((root / "a.txt").exists())
            agent.confirm(True)
            self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "hi")
            self.assertIn("写好了", agent.transcript[-1]["text"])

    def test_deny_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gateway = ScriptedGateway(
                [
                    Turn("", [ToolCall("write_file", {"path": "a.txt", "content": "hi"})]),
                    Turn("好，不写了"),
                ]
            )
            agent = Agent(gateway, root)
            agent.user_say("写个文件")
            agent.confirm(False)
            self.assertFalse((root / "a.txt").exists())
            self.assertIn("好，不写了", agent.transcript[-1]["text"])

    def test_read_runs_without_confirm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.txt").write_text("data", encoding="utf-8")
            gateway = ScriptedGateway(
                [
                    Turn("", [ToolCall("read_file", {"path": "a.txt"})]),
                    Turn("文件里是 data"),
                ]
            )
            agent = Agent(gateway, root)
            agent.user_say("看看 a.txt")
            self.assertIsNone(agent.pending)
            self.assertIn("data", agent.terminal[-1])
            self.assertIn("文件里是 data", agent.transcript[-1]["text"])


if __name__ == "__main__":
    unittest.main()
