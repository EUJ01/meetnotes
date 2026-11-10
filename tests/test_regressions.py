"""Regression tests for the issues found in the first code review."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from meetnotes import llm, summarize, update
from meetnotes.asr.common import collapse_loops
from meetnotes.publish import Unavailable, publish
from meetnotes.publish.folder import Folder
from meetnotes.publish.telegram import Telegram
from tests.fake_server import FakeServer
from tests.test_publish import OK_MSG, make_update

BODY = "## Summary\n\n- a\n\n## To do before the next update\n\n- [ ] b\n\n## Open questions\n\n- None."


class Review(unittest.TestCase):
    def test_loop_keeps_next_word(self):
        self.assertEqual(collapse_loops("no no no no nothing"), "no nothing")
        self.assertEqual(collapse_loops("no no no nope"), "no no no nope")

    def test_cut_off_reply(self):
        srv = FakeServer([(200, {"choices": [{"message": {"content": BODY}, "finish_reason": "length"}]}, None)])
        try:
            with self.assertRaises(llm.LLMError) as e:
                llm.chat({"base_url": srv.url, "model": "m", "timeout": 5}, [], sleep=lambda s: None)
            self.assertIn("max_tokens", str(e.exception))
        finally:
            srv.close()

    def test_think_without_opening_tag(self):
        self.assertEqual(summarize.clean_reply("plan the answer...</think>\n" + BODY), BODY)

    def test_notes_of_notes(self):
        rounds = []

        def chat(cfg, messages):
            if "part" in messages[0]["content"][:80]:
                rounds.append(1)
                return "- " + "note " * 200  # long notes force a second round
            return BODY
        summarize.summarize(" ".join(f"Sentence {i} here." for i in range(400)), {"max_input_chars": 1500},
                            chat=chat, log=lambda m: None)
        self.assertGreater(len(rounds), 6)

    def test_same_name_other_size_gets_new_file(self):
        with tempfile.TemporaryDirectory() as d:
            day = dt.date(2026, 10, 20)
            a = {"source": "zoom_0.mp4", "size": "100"}
            first = update.path_for(d, "demo", day, update.source_id(a))
            update.write(first, update.header("demo", day, a, 5, "x") + BODY)
            self.assertEqual(update.path_for(d, "demo", day, update.source_id(a)), first)
            other = update.path_for(d, "demo", day, update.source_id({"source": "zoom_0.mp4", "size": "200"}))
            self.assertNotEqual(other, first)

    def test_empty_skeleton_not_published(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as drive:
            day = dt.date(2026, 10, 20)
            make_update(ws, text=update.header("demo", day, {"source": "a"}, 1, "an agent") + update.skeleton())
            logs = []
            publish({}, ws, chosen=[Folder(drive)], log=logs.append)
            self.assertIn("still empty", logs[0])
            self.assertEqual(list(Path(drive).rglob("*.md")), [])

    def test_missing_token_does_not_block_folder(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as drive:
            make_update(ws)
            n = publish({}, ws, chosen=[Unavailable("telegram", "no token"), Folder(drive)], log=lambda m: None)
            self.assertEqual(n, 1)
            self.assertEqual(len(list(Path(drive).rglob("*_update.md"))), 1)

    def test_new_folder_gets_the_files(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            make_update(ws)
            publish({}, ws, chosen=[Folder(d1)], log=lambda m: None)
            publish({}, ws, chosen=[Folder(d2)], log=lambda m: None)
            self.assertEqual(len(list(Path(d2).rglob("*_update.md"))), 1)

    def test_os_error_is_counted(self):
        class Broken(Folder):
            def send(self, *a):
                raise PermissionError("locked by the sync client")
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as d:
            make_update(ws)
            make_update(ws, name="79738978_2026-10-21_update.md")
            self.assertEqual(publish({}, ws, chosen=[Broken(d)], log=lambda m: None), 2)

    def test_edit_rate_limited_does_not_post_twice(self):
        srv = FakeServer([(429, {"ok": False, "description": "Too Many Requests: retry after 5"}, None), OK_MSG])
        try:
            from meetnotes.publish import PublishError
            with self.assertRaises(PublishError):
                Telegram("t", {"demo": "-1"}, api=srv.url).send(Path(__file__), "demo", "2026-10-20", "5")
            self.assertEqual(len(srv.requests), 1)
        finally:
            srv.close()


class Security(unittest.TestCase):
    def test_redirect_is_not_followed(self):
        import os
        os.environ["MEETNOTES_TEST_KEY"] = "sk-secret"
        target = FakeServer([(200, {"choices": [{"message": {"content": "x"}}]}, None)])
        srv = FakeServer([(302, {}, {"Location": target.url + "/v1/chat/completions"})])
        try:
            with self.assertRaises(llm.LLMError) as e:
                llm.chat({"base_url": srv.url, "model": "m", "api_key_env": "MEETNOTES_TEST_KEY"}, [], sleep=lambda s: None)
            self.assertIn("redirect", str(e.exception))
            self.assertEqual(target.requests, [])  # the key never reached the other server
        finally:
            srv.close()
            target.close()
            del os.environ["MEETNOTES_TEST_KEY"]

    def test_no_key_over_plain_http(self):
        import os
        os.environ["MEETNOTES_TEST_KEY"] = "sk-secret"
        try:
            with self.assertRaises(llm.LLMError) as e:
                llm.chat({"base_url": "http://example.com/v1", "model": "m", "api_key_env": "MEETNOTES_TEST_KEY"}, [])
            self.assertIn("plain http", str(e.exception))
        finally:
            del os.environ["MEETNOTES_TEST_KEY"]


class FirstRun(unittest.TestCase):
    def test_minutes_saved_into_a_new_folder(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "projects" / "new" / "x.minutes.md"
            summarize.summarize(" ".join(f"Sentence {i}." for i in range(300)), {"max_input_chars": 1000},
                                chat=lambda c, m: BODY if "three sections" in m[0]["content"] else "- note",
                                log=lambda m: None, notes_out=out)
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
