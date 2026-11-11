"""The review agent: the model checks its draft update against the transcript with two tools, then returns a
corrected update. The minutes step compresses the meeting, so points get lost or garbled; the tools give the model
a way back to the source text (the fix that context-aware merging research found against hallucinations that grow
at each merge)."""
import json
import re

from meetnotes import llm
from meetnotes.summarize import SENTENCE_END, background_block, clean_reply, missing, prompt, split

PART_CHARS = 6000  # a part returned by read_part: big enough to read a topic, small enough for several reads
BUDGET = 6  # tool calls per review
TOOLS = [
    {"type": "function", "function": {
        "name": "search_transcript",
        "description": "Find transcript passages that contain the given words (any order, any case). Returns up to "
                       "4 passages with their part number. English terms may be written in another script in the "
                       "transcript: if a search finds nothing, try other words or read the part.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_part",
        "description": "Read one part of the transcript in full. Parts are numbered from 1.",
        "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}},
]


def search(parts, query, top=4, width=3):
    """Passages of `width` sentences, ranked by how many distinct query words they contain."""
    words = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 1}
    if not words:
        return "Give one or more words to search for."
    hits = []
    for n, part in enumerate(parts, 1):
        sents = SENTENCE_END.split(part)
        for i in range(0, len(sents), width):
            passage = " ".join(sents[i:i + width])
            low = passage.lower()
            score = sum(w in low for w in words)
            if score:
                hits.append((score, n, passage))
    if not hits:
        return "No passage contains those words. Try other words, or read a part."
    hits.sort(key=lambda h: -h[0])
    return "\n\n".join(f"[part {n}] {p[:600]}" for _, n, p in hits[:top])


def run_tool(call, parts):
    try:
        args = json.loads(call["arguments"] or "{}")
    except ValueError:
        return "The arguments were not valid JSON."
    if call["name"] == "search_transcript":
        return search(parts, str(args.get("query", "")))
    if call["name"] == "read_part":
        try:
            n = int(args.get("n"))
        except (TypeError, ValueError):
            return "Give the part number n."
        return parts[n - 1] if 1 <= n <= len(parts) else f"There are {len(parts)} parts, numbered from 1."
    return f"Unknown tool {call['name']}."


def review(draft, transcript, cfg, background="", log=print, complete=llm.complete, budget=BUDGET, minutes=""):
    """Return the corrected update body. If the review fails in any way, the draft is kept: the review must never
    make the result worse than no review."""
    parts = split(transcript, PART_CHARS, overlap=0)
    tools_text = (f"You have two tools: search_transcript and read_part. Use at most {budget} tool calls, on the "
                  "points that matter most for the to-do list.")
    system = prompt("review", parts=len(parts), context=background_block(background), tools=tools_text,
                    output_language=cfg.get("output_language") or "English")
    given = f"Minutes taken from the meeting, part by part:\n\n{minutes.strip()}\n\n" if minutes.strip() else ""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": given + "Draft update:\n\n" + draft}]
    used = 0
    try:
        for _ in range(budget + 2):
            offer = TOOLS if used < budget else None
            reply = complete(cfg, messages, tools=offer, log=log)
            calls = reply["tool_calls"][:budget - used] if offer else []  # one reply can ask for several calls
            if not calls:
                body = clean_reply(reply["content"])
                if missing(body):
                    log("review: the reply missed a section; keeping the draft")
                    return draft
                log(f"review: done after {used} tool calls")
                return body
            for i, c in enumerate(calls):
                c["id"] = c["id"] or f"call_{used + i}"
            messages.append({"role": "assistant", "content": reply["content"] or "", "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                for c in calls]})
            for c in calls:
                used += 1
                log(f"review: {c['name']} {c['arguments'][:80]}")
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": run_tool(c, parts)})
            if used >= budget:
                messages.append({"role": "user", "content": "No more tool calls. Return the whole corrected update now."})
    except llm.LLMError as e:
        log(f"review skipped ({e}); keeping the draft")
        return draft
    log("review: no final answer; keeping the draft")
    return draft
