import unittest

from yxbot.gateway import GatewayError, parse_response


class ParseTests(unittest.TestCase):
    def test_reads_tool_call(self):
        turn = parse_response(
            {
                "code": 0,
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "1",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": "{\"path\":\"a.txt\"}",
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        )
        self.assertEqual(turn.tool_calls[0].name, "read_file")
        self.assertEqual(turn.tool_calls[0].arguments["path"], "a.txt")

    def test_stream_assembler_collects_deltas(self):
        from yxbot.gateway import StreamAssembler

        assembler = StreamAssembler()
        self.assertEqual(assembler.feed_line('data: {"choices":[{"delta":{"content":"你"}}]}'), "你")
        self.assertEqual(assembler.feed_line('data: {"choices":[{"delta":{"content":"好"}}]}'), "好")
        self.assertEqual(assembler.feed_line("data: [DONE]"), "")
        self.assertEqual(assembler.finish().content, "你好")

    def test_reads_json_tool_in_content(self):
        turn = parse_response(
            {
                "choices": [
                    {"message": {"content": '{"tool":"list_dir","args":{"path":"."}}'}}
                ]
            }
        )
        self.assertEqual(turn.tool_calls[0].name, "list_dir")
        self.assertEqual(turn.content, "")

    def test_rejects_nonzero_code(self):
        with self.assertRaises(GatewayError):
            parse_response({"code": 12, "choices": [{"message": {"content": "x"}}]})


if __name__ == "__main__":
    unittest.main()
