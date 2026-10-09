import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from yxbot.app import create_app
from yxbot.loop import Agent


class SilentGateway:
    def complete(self, messages, tools):
        raise AssertionError("this test must not call the model")


class AppTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        agent = Agent(SilentGateway(), Path(self._tmp.name))
        self.client = TestClient(create_app(agent))

    def tearDown(self):
        self._tmp.cleanup()

    def test_settings_do_not_include_the_key(self):
        response = self.client.get("/api/settings")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("api_key", body)
        self.assertIn("key_set", body)

    def test_page_opens(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("YXBot", response.text)


if __name__ == "__main__":
    unittest.main()
