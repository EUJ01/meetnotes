import json
import unittest

from meetnotes import agent, llm

BODY = "## Summary\n\n- a\n\n## To do before the next update\n\n- [ ] b\n\n## Open questions\n\n- None."
TRANSCRIPT = "We start the toy experiment next week. Then the pipeline. The DPO line comes later. " * 20


def scripted(replies):
    """A fake llm.complete that returns the replies in order and records what it was sent."""
    sent = []

    def complete(cfg, messages, tools=None, log=None):
        sent.append({"messages": [dict(m) for m in messages], "tools": tools})
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return complete, sent


def call(name, **args):
    return {"content": "", "tool_calls": [{"id": "", "name": name, "arguments": json.dumps(args)}]}


class Review(unittest.TestCase):
    def test_tools_then_answer(self):
        fixed = BODY.replace("- [ ] b", "- [ ] Run the toy experiment next week")
        complete, sent = scripted([call("search_transcript", query="toy experiment"), call("read_part", n=1),
                                   {"content": fixed, "tool_calls": []}])
        out = agent.review(BODY, TRANSCRIPT, {}, complete=complete, log=lambda m: None)
        self.assertEqual(out, fixed)
        tool_msgs = [m for m in sent[-1]["messages"] if m["role"] == "tool"]
        self.assertIn("toy experiment", tool_msgs[0]["content"])
        self.assertTrue(tool_msgs[1]["content"].startswith("We start"))
        self.assertTrue(all(m["tool_call_id"] for m in tool_msgs))

    def test_budget_then_no_tools_offered(self):
        complete, sent = scripted([call("read_part", n=1), call("read_part", n=2), {"content": BODY, "tool_calls": []}])
        agent.review(BODY, TRANSCRIPT, {}, complete=complete, log=lambda m: None, budget=2)
        self.assertIsNone(sent[-1]["tools"])
        self.assertIn("No more tool calls", sent[-1]["messages"][-1]["content"])

    def test_bad_answer_keeps_draft(self):
        complete, _ = scripted([{"content": "I think it is fine.", "tool_calls": []}])
        self.assertEqual(agent.review(BODY, TRANSCRIPT, {}, complete=complete, log=lambda m: None), BODY)

    def test_server_error_keeps_draft(self):
        complete, _ = scripted([llm.LLMError("HTTP 400: tools not supported")])
        self.assertEqual(agent.review(BODY, TRANSCRIPT, {}, complete=complete, log=lambda m: None), BODY)

    def test_tool_errors_are_answers(self):
        parts = ["a. b. c."]
        self.assertIn("1 parts", agent.run_tool({"name": "read_part", "arguments": '{"n": 5}'}, parts))
        self.assertIn("not valid JSON", agent.run_tool({"name": "read_part", "arguments": "{n:"}, parts))
        self.assertIn("Unknown tool", agent.run_tool({"name": "rm", "arguments": "{}"}, parts))
        self.assertIn("No passage", agent.search(parts, "zebra"))


if __name__ == "__main__":
    unittest.main()
