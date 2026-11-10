import tempfile
import unittest
from pathlib import Path

from meetnotes import cli, summarize, transcript


class Translate(unittest.TestCase):
    def test_parts_in_order(self):
        text = " ".join(f"বাক্য {i}।" for i in range(2000))
        calls = []

        def chat(cfg, messages):
            calls.append(messages[1]["content"])
            return f"part {len(calls)}"
        out = summarize.translate(text, {}, chat=chat, log=lambda m: None)
        self.assertGreater(len(calls), 3)
        self.assertTrue(out.startswith("part 1\n\npart 2"))
        self.assertTrue(all(len(c) <= summarize.TRANSLATE_CHARS for c in calls))

    def test_auto_rule(self):
        w = cli._wants_translation
        self.assertTrue(w({}, {"language": "bn"}))
        self.assertFalse(w({}, {"language": "en"}))
        self.assertFalse(w({}, {}))  # unknown language: leave it
        self.assertFalse(w({"output_language": "German"}, {"language": "bn"}))
        self.assertTrue(w({"translate": True}, {}))
        self.assertFalse(w({"translate": False}, {"language": "bn"}))

    def test_cache_reused_until_text_or_model_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "m.md"
            transcript.write(path, {"source": "m.mp4", "language": "bn"}, "আমি।")
            calls = []
            orig = summarize.translate
            summarize.translate = lambda text, cfg, **kw: calls.append(1) or "I."
            try:
                cfg = {"llm": {"model": "a"}}
                self.assertEqual(cli._translated(path, {"language": "bn"}, "আমি।", cfg, ""), "I.")
                cli._translated(path, {"language": "bn"}, "আমি।", cfg, "")
                self.assertEqual(len(calls), 1)  # reused
                cli._translated(path, {"language": "bn"}, "আমি।", {"llm": {"model": "b"}}, "")
                self.assertEqual(len(calls), 2)  # another model: translated again
            finally:
                summarize.translate = orig
            self.assertTrue((Path(d) / "m.translated.md").exists())


if __name__ == "__main__":
    unittest.main()
