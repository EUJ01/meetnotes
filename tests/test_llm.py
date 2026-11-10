import json
import os
import socket
import unittest

from meetnotes import llm
from tests.fake_server import FakeServer, chat_reply


def cfg(url, **kw):
    return {"base_url": url + "/v1/", "model": "m", "api_key_env": "", "max_tokens": 100, "temperature": None,
            "timeout": 5, **kw}


class Chat(unittest.TestCase):
    def setUp(self):
        self.waits = []

    def sleep(self, s):
        self.waits.append(s)

    def test_ok_without_key(self):
        srv = FakeServer([chat_reply("hi")])
        try:
            self.assertEqual(llm.chat(cfg(srv.url), [{"role": "user", "content": "x"}], sleep=self.sleep), "hi")
            req = srv.requests[0]
            self.assertEqual(req["path"], "/v1/chat/completions")
            self.assertNotIn("Authorization", req["headers"])
            self.assertNotIn("temperature", json.loads(req["body"]))
        finally:
            srv.close()

    def test_key_and_temperature(self):
        os.environ["MEETNOTES_TEST_KEY"] = "sk-test"
        srv = FakeServer([chat_reply("hi")])
        try:
            llm.chat(cfg(srv.url, api_key_env="MEETNOTES_TEST_KEY", temperature=0.2), [], sleep=self.sleep)
            self.assertEqual(srv.requests[0]["headers"]["Authorization"], "Bearer sk-test")
            self.assertEqual(json.loads(srv.requests[0]["body"])["temperature"], 0.2)
        finally:
            srv.close()
            del os.environ["MEETNOTES_TEST_KEY"]

    def test_429_then_ok(self):
        srv = FakeServer([(429, {"error": "slow down"}, {"Retry-After": "1"}), chat_reply("ok")])
        try:
            self.assertEqual(llm.chat(cfg(srv.url), [], sleep=self.sleep), "ok")
            self.assertEqual(self.waits, [1.0])
        finally:
            srv.close()

    def test_500_three_times(self):
        srv = FakeServer([(500, {"error": "boom"}, None)])
        try:
            with self.assertRaises(llm.LLMError) as e:
                llm.chat(cfg(srv.url), [], sleep=self.sleep)
            self.assertIn("HTTP 500", str(e.exception))
            self.assertEqual(len(srv.requests), 3)
        finally:
            srv.close()

    def test_401_no_retry(self):
        srv = FakeServer([(401, {"error": "bad key"}, None)])
        try:
            with self.assertRaises(llm.LLMError) as e:
                llm.chat(cfg(srv.url), [], sleep=self.sleep)
            self.assertIn("API key", str(e.exception))
            self.assertEqual(len(srv.requests), 1)
        finally:
            srv.close()

    def test_unreachable(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        with self.assertRaises(llm.LLMError) as e:
            llm.chat(cfg(f"http://127.0.0.1:{port}"), [], sleep=self.sleep)
        self.assertIn("cannot reach", str(e.exception))

    def test_empty_and_odd_replies(self):
        for reply in (chat_reply(""), (200, {"choices": [{"message": {"content": None}}]}, None), (200, {"x": 1}, None)):
            srv = FakeServer([reply])
            try:
                with self.assertRaises(llm.LLMError):
                    llm.chat(cfg(srv.url), [], sleep=self.sleep)
            finally:
                srv.close()

    def test_not_configured(self):
        with self.assertRaises(llm.LLMError) as e:
            llm.chat({"model": "m", "base_url": ""}, [])
        self.assertEqual(e.exception.code, 2)

    def test_stream(self):
        events = [{"choices": [{"delta": {"reasoning_content": "hmm"}}]}, {"choices": [{"delta": {"content": "Hel"}}]},
                  {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]}]
        sse = "".join(f"data: {json.dumps(e)}\n\n" for e in events).encode() + b"data: [DONE]\n\n"
        srv = FakeServer([(200, sse, None)])
        try:
            self.assertEqual(llm.chat(cfg(srv.url), [], sleep=self.sleep), "Hello")
            self.assertTrue(json.loads(srv.requests[0]["body"])["stream"])
        finally:
            srv.close()

    def test_stream_cut_off(self):
        sse = b'data: {"choices": [{"delta": {"content": "## Sum"}, "finish_reason": "length"}]}\n\ndata: [DONE]\n\n'
        srv = FakeServer([(200, sse, None)])
        try:
            with self.assertRaises(llm.LLMError):
                llm.chat(cfg(srv.url), [], sleep=self.sleep)
        finally:
            srv.close()

    def test_models(self):
        srv = FakeServer([(200, {"data": [{"id": "a"}, {"id": "m"}]}, None)])
        try:
            self.assertEqual(llm.models(cfg(srv.url)), ["a", "m"])
        finally:
            srv.close()


if __name__ == "__main__":
    unittest.main()
