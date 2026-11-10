import datetime as dt
import tempfile
import unittest
from pathlib import Path

from meetnotes import Fail, audio, config, glossary, summarize, transcript, update
from meetnotes.asr.common import collapse_loops, run_batches


class Naming(unittest.TestCase):
    def test_key_sorts_newest_first(self):
        self.assertEqual(update.key(dt.date(2026, 10, 20)), "79738979")
        self.assertLess(update.key(dt.date(2026, 10, 21)), update.key(dt.date(2026, 10, 20)))

    def test_same_day(self):
        with tempfile.TemporaryDirectory() as d:
            day = dt.date(2026, 10, 20)
            first = update.path_for(d, "demo", day, "a.mp4")
            self.assertEqual(first.name, "79738979_2026-10-20_update.md")
            update.write(first, update.header("demo", day, {"source": "a.mp4"}, 10, "x") + update.skeleton())
            self.assertEqual(update.path_for(d, "demo", day, "a.mp4"), first)  # same source: replace
            second = update.path_for(d, "demo", day, "b.mp4")
            self.assertEqual(second.name, "79738979_2026-10-20_2_update.md")  # other source: numbered
            self.assertTrue(second.name.endswith("_update.md"))
            self.assertLess(second.name, first.name)  # the later one sorts first

    def test_project_names(self):
        for bad in ("", "../x", "a/b", "a b", ".hidden", "a..b"):
            with self.assertRaises(Fail):
                update.check_project(bad)
        self.assertEqual(update.check_project("team_2026.v1-x"), "team_2026.v1-x")

    def test_bad_date(self):
        with self.assertRaises(Fail):
            update.parse_date("1/10/26")

    def test_skeleton_has_headings(self):
        self.assertEqual(summarize.missing(update.skeleton()), [])


class Chunking(unittest.TestCase):
    def test_cuts_at_latest_pause(self):
        self.assertEqual(audio.cut_points([5, 12, 18, 30, 39], 50, 20), [18, 30])
        self.assertEqual(audio.cut_points([5, 12, 18, 30, 39], 51, 20), [18, 30, 39])

    def test_short_clip_has_no_cut(self):
        self.assertEqual(audio.cut_points([3], 20, 20), [])
        self.assertEqual(audio.cut_points([], 0.5, 20), [])

    def test_no_pauses_hard_cuts(self):
        self.assertEqual(audio.cut_points([], 65, 20), [20, 40, 60])

    def test_quiet(self):
        self.assertTrue(audio.is_quiet(-60, -30))
        self.assertFalse(audio.is_quiet(-40, -30))


class Batches(unittest.TestCase):
    def test_halves_on_oom(self):
        sizes = []

        def fn(part):
            sizes.append(len(part))
            if len(part) > 2:
                raise RuntimeError("HIP out of memory. Tried to allocate")
            return [x * 2 for x in part]

        out = run_batches(list(range(7)), 8, fn, lambda: None, lambda m: None)
        self.assertEqual(out, [x * 2 for x in range(7)])
        self.assertEqual(sizes[:3], [7, 4, 2])

    def test_other_errors_raise(self):
        def fn(part):
            raise RuntimeError("shape mismatch")
        with self.assertRaises(RuntimeError):
            run_batches([1], 8, fn, lambda: None, lambda m: None)

    def test_loops(self):
        self.assertEqual(collapse_loops("so we go we go we go we go now"), "so we go now")


class Glossary(unittest.TestCase):
    def test_self_check(self):  # the self-check from the original script
        g = {"drop": ["xx.*?yy"], "fixes": {"ও মুখ": "অমুক"}, "guesses": {"সাবাড়ি": "summary"},
             "terms": {"ওয়ার্ড": "word", "ওয়ার্ডস": "words", "আই এম": "I am", "ফ্ল্যাশ কার্ড": "flashcard"}, "doubtful": []}
        out, hits, dropped = glossary.clean("a xx junk yy b আই এম ও মুখ ওয়ার্ডসগুলো ওয়ার্ড -এর সাবাড়িটা ফ্ল্যাশ  কার্ডে ওয়ার্ডে", g)
        self.assertEqual(dropped, 1)
        self.assertEqual(out, "a [unclear] b I am অমুক words-গুলো word-এর summary-টা flashcard-এ word-এ")
        self.assertIn("summary", glossary.report("x.mp4", "সাবাড়িটা", hits, dropped, g, "g.json"))

    def test_example_file_loads(self):
        g = glossary.load(Path(__file__).parents[1] / "glossary.example.json")
        self.assertGreater(len(g["terms"]), 20)


class Transcript(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            meta = {"source": "a b.mp4", "source_path": "C:\\x y\\a b.mp4", "size": 5, "recorded": "2026-10-20",
                    "duration": 61.5, "limit": 0, "language": "bn", "model": "m"}
            transcript.write(p, meta, "নমস্কার: hello\n")
            got, text = transcript.read(p)
            self.assertEqual(got["source_path"], "C:\\x y\\a b.mp4")
            self.assertEqual(text, "নমস্কার: hello")
            self.assertFalse(p.with_name("t.md.tmp").exists())

    def test_plain_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            p.write_text("just text\n---\nmore", encoding="utf-8")
            self.assertEqual(transcript.read(p), ({}, "just text\n---\nmore"))


class Replies(unittest.TestCase):
    BODY = "## Summary\n\n- a\n\n## To do before the next update\n\n### 1. X\n- [ ] b\n\n## Open questions\n\n- None."

    def test_think_fence_title(self):
        raw = f"<think>hmm\nlong</think>\n```markdown\n# Update\n{self.BODY}\n```"
        self.assertEqual(summarize.clean_reply(raw), self.BODY)

    def test_unfinished_think(self):
        with self.assertRaises(summarize.SummaryError):
            summarize.clean_reply("<think>still going")

    def test_missing(self):
        self.assertEqual(summarize.missing("## Summary\n- a"), ["## To do before the next update", "## Open questions"])

    def test_retry_then_ok(self):
        replies = iter(["## Summary\n- a", self.BODY])
        body = summarize.summarize("text.", {}, chat=lambda cfg, m: next(replies), log=lambda m: None)
        self.assertEqual(body, self.BODY)

    def test_retry_then_fail(self):
        with self.assertRaises(summarize.SummaryError) as e:
            summarize.summarize("text.", {}, chat=lambda cfg, m: "nothing", log=lambda m: None)
        self.assertEqual(e.exception.reply, "nothing")

    def test_map_reduce(self):
        calls = []

        def chat(cfg, messages):
            calls.append(messages[0]["content"])
            return "- note" if "part" in messages[0]["content"][:80] else self.BODY
        text = " ".join(f"Sentence number {i} is here." for i in range(200))
        summarize.summarize(text, {"max_input_chars": 1000}, chat=chat, log=lambda m: None)
        self.assertGreater(len(calls), 3)
        self.assertIn("three sections", calls[-1])

    def test_empty(self):
        with self.assertRaises(summarize.SummaryError):
            summarize.summarize("  ", {}, chat=lambda c, m: "", log=lambda m: None)


class Split(unittest.TestCase):
    def test_short_is_one_part(self):
        self.assertEqual(summarize.split("a. b.", 100), ["a. b."])

    def test_bangla_sentence_ends_and_overlap(self):
        text = " ".join(["আমি ভাত খাই।"] * 300)
        parts = summarize.split(text, 500)
        self.assertGreater(len(parts), 5)
        self.assertTrue(all(p.endswith("।") for p in parts))
        self.assertTrue(all(len(p) <= 500 + summarize.OVERLAP for p in parts))
        self.assertTrue(parts[1].startswith("আমি") or parts[1].startswith("ভাত") or parts[1].startswith("খাই"))

    def test_long_sentence_is_cut(self):
        parts = summarize.split("x" * 2500, 1000, overlap=0)
        self.assertEqual("".join(parts), "x" * 2500)


class Config(unittest.TestCase):
    def test_defaults_and_unknown_key(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.toml"
            p.write_text('[llm]\nmodel = "m"\n[clean]\nglossary = "g.json"\n', encoding="utf-8")
            cfg, ws = config.load(p)
            self.assertEqual(cfg["llm"]["model"], "m")
            self.assertEqual(cfg["transcribe"]["batch"], 8)
            self.assertEqual(Path(cfg["clean"]["glossary"]), Path(d).resolve() / "g.json")
            self.assertEqual(ws, Path(d).resolve())
            p.write_text('[llm]\nmodle = "m"\n', encoding="utf-8")
            with self.assertRaises(Fail):
                config.load(p)

    def test_example_config_loads(self):
        cfg, _ = config.load(Path(__file__).parents[1] / "config.example.toml")
        self.assertEqual(cfg["publish"]["telegram"]["chats"], {})


if __name__ == "__main__":
    unittest.main()
