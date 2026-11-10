import tempfile
import unittest
from pathlib import Path

from yxbot.gateway import Turn
from yxbot.loop import Agent
from yxbot.sessions import SessionStore


class ScriptedGateway:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        return Turn("收到")

    def suggest_title(self, text):
        return "申报指南摘要"


class SessionTests(unittest.TestCase):
    def test_saves_reopens_and_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            agent = Agent(ScriptedGateway(), Path(tmp), store)
            agent.user_say("请总结这份申报指南的条件")
            self.assertEqual(len(store.list_sessions()), 1)
            saved = store.latest()
            self.assertEqual(saved["title"], "申报指南摘要")
            self.assertNotIn("api_key", saved)
            first_id = agent.session_id

            agent.start_new()
            agent.user_say("另一段对话")
            self.assertEqual(len(store.list_sessions()), 2)
            self.assertNotEqual(agent.session_id, first_id)

            agent.open_session(first_id)
            self.assertEqual(agent.session_id, first_id)
            self.assertIn("申报指南", agent.transcript[0]["text"])

            agent.delete_session(first_id)
            self.assertEqual(len(store.list_sessions()), 1)
            self.assertNotEqual(agent.session_id, first_id)
            self.assertIn("另一段对话", agent.transcript[0]["text"])

    def test_custom_title_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            agent = Agent(ScriptedGateway(), Path(tmp), store)
            agent.user_say("请总结这份申报指南的条件")
            agent.rename(agent.session_id, "申报材料")
            agent.user_say("再看一下截止时间")
            self.assertEqual(store.latest()["title"], "申报材料")

    def test_delete_missing_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            agent = Agent(ScriptedGateway(), Path(tmp), store)
            with self.assertRaises(Exception):
                agent.delete_session("missing")


if __name__ == "__main__":
    unittest.main()
