import tempfile
import unittest
from pathlib import Path

from meetnotes.publish import Ledger, publish
from meetnotes.publish.folder import Folder
from meetnotes.publish.telegram import Telegram
from tests.fake_server import FakeServer

OK_MSG = (200, {"ok": True, "result": {"message_id": 7}}, None)


def make_update(ws, project="demo", name="79738979_2026-10-20_update.md", text="v1"):
    p = Path(ws) / "projects" / project / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class TelegramTarget(unittest.TestCase):
    def test_new_unchanged_changed(self):
        srv = FakeServer([OK_MSG])
        try:
            with tempfile.TemporaryDirectory() as ws:
                f = make_update(ws)
                tg = Telegram("123:abc", {"demo": "-100"}, api=srv.url)
                self.assertEqual(publish({}, ws, chosen=[tg], log=lambda m: None), 0)
                self.assertTrue(srv.requests[-1]["path"].endswith("/sendDocument"))
                self.assertIn(b"79738979_2026-10-20_update.md", srv.requests[-1]["body"])
                publish({}, ws, chosen=[tg], log=lambda m: None)
                self.assertEqual(len(srv.requests), 1)  # unchanged: nothing sent
                f.write_text("v2", encoding="utf-8")
                publish({}, ws, chosen=[tg], log=lambda m: None)
                self.assertTrue(srv.requests[-1]["path"].endswith("/editMessageMedia"))
                self.assertIn(b'name="message_id"\r\n\r\n7', srv.requests[-1]["body"])
        finally:
            srv.close()

    def test_edit_fails_then_new_copy(self):
        srv = FakeServer([(400, {"ok": False, "description": "Bad Request: message to edit not found"}, None), OK_MSG])
        try:
            msg, did = Telegram("t", {"demo": "-1"}, api=srv.url).send(Path(__file__), "demo", "2026-10-20", "5")
            self.assertEqual((msg, did), ("7", "posted a revised copy of"))
        finally:
            srv.close()

    def test_error_hint_and_failure_count(self):
        srv = FakeServer([(400, {"ok": False, "description": "Bad Request: chat not found"}, None)])
        try:
            with tempfile.TemporaryDirectory() as ws:
                make_update(ws)
                logs = []
                n = publish({}, ws, chosen=[Telegram("t", {"demo": "-1"}, api=srv.url)], log=logs.append)
                self.assertEqual(n, 1)
                self.assertIn("add the bot", logs[-1])
                self.assertFalse((Path(ws) / ".meetnotes" / "ledger.tsv").exists())  # retried next time
        finally:
            srv.close()

    def test_project_without_chat_is_skipped(self):
        with tempfile.TemporaryDirectory() as ws:
            make_update(ws, project="other")
            logs = []
            self.assertEqual(publish({}, ws, chosen=[Telegram("t", {"demo": "-1"}, api="http://127.0.0.1:9")],
                                     log=logs.append), 0)
            self.assertIn("no chat id", logs[0])


class FolderTarget(unittest.TestCase):
    def test_copy_once_then_on_change(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as drive:
            f = make_update(ws)
            logs = []
            publish({}, ws, chosen=[Folder(drive)], log=logs.append)
            dest = Path(drive) / "demo" / f.name
            self.assertEqual(dest.read_text(encoding="utf-8"), "v1")
            self.assertEqual(list((Path(drive) / "demo").glob(".*")), [])  # no temp file left
            publish({}, ws, chosen=[Folder(drive)], log=logs.append)
            self.assertEqual(logs[1:], ["publish: nothing new to send"])
            f.write_text("v2", encoding="utf-8")
            publish({}, ws, chosen=[Folder(drive)], log=logs.append)
            self.assertEqual(dest.read_text(encoding="utf-8"), "v2")

    def test_missing_root(self):
        with tempfile.TemporaryDirectory() as ws:
            make_update(ws)
            missing = Path(ws) / "not-mounted"
            self.assertEqual(publish({}, ws, chosen=[Folder(missing)], log=lambda m: None), 1)
            self.assertFalse(missing.exists())

    def test_targets_are_independent(self):
        with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as drive:
            make_update(ws)
            n = publish({}, ws, chosen=[Folder(Path(ws) / "nope"), Folder(drive)], log=lambda m: None)
            self.assertEqual(n, 1)
            self.assertEqual(len(list(Path(drive).rglob("*_update.md"))), 1)


class LedgerFile(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            led = Ledger(Path(d) / "l.tsv")
            led.set("demo/a_update.md", "telegram", "abc", "7")
            self.assertEqual(Ledger(Path(d) / "l.tsv").get("demo/a_update.md", "telegram"), ("abc", "7"))


if __name__ == "__main__":
    unittest.main()
