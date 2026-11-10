"""Transcript text -> the body of an update file, with any OpenAI-compatible LLM."""
import re
from importlib import resources
from pathlib import Path

from meetnotes import Fail, llm

HEADINGS = ["## Summary", "## To do before the next update", "## Open questions"]
SENTENCE_END = re.compile(r"(?<=[.?!।])\s+")
OVERLAP = 300  # characters of the previous part repeated at the start of the next one


class SummaryError(Fail):
    def __init__(self, message, reply=""):
        super().__init__(message)
        self.reply = reply


def prompt(name, **values):
    text = resources.files("meetnotes").joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def clean_reply(text):
    """Drop reasoning blocks (Qwen3, DeepSeek-R1 put <think>...</think> in the content), a wrapping code fence,
    and a leading title the model added despite the prompt."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if "</think>" in text:  # some servers strip the opening tag and send "reasoning</think>answer"
        text = text.rsplit("</think>", 1)[1].strip()
    if text.startswith("<think>"):
        raise SummaryError("the model's reasoning did not finish: raise [llm] max_tokens", text)
    fence = re.fullmatch(r"```[\w-]*\n(.*)\n```", text, flags=re.S)
    if fence:
        text = fence[1].strip()
    return re.sub(r"\A(#\s[^\n]*\n+)+", "", text).strip()


def missing(body):
    return [h for h in HEADINGS if not re.search(rf"^{re.escape(h)}\s*$", body, flags=re.M)]


def split(text, limit, overlap=OVERLAP):
    """Parts of at most about `limit` characters, cut at sentence ends (. ? ! and the Bangla ।). Each part after
    the first starts with up to `overlap` characters of the one before, so no point is cut in half without context.
    A single sentence longer than the limit is cut hard."""
    if len(text) <= limit:
        return [text]
    sentences = []
    for s in SENTENCE_END.split(text):
        sentences += [s[i:i + limit] for i in range(0, len(s), limit)] or [s]
    parts, cur = [], ""
    for s in sentences:
        if cur and len(cur) + 1 + len(s) > limit:
            parts.append(cur)
            tail = cur[-overlap:] if overlap else ""  # cur[-0:] would be the whole part
            cur = tail[tail.find(" ") + 1:] if " " in tail else tail  # start the overlap at a word
        cur = f"{cur} {s}".strip()
    if cur:
        parts.append(cur)
    return parts


def background_block(background):
    """The user's project context, framed so the model uses it to read terms but never reports it as said."""
    if not background.strip():
        return ""
    return ("\nBackground from the user, to help you read the transcript. It is not part of this meeting: "
            "never report it as something that was said.\n<background>\n" + background.strip() + "\n</background>\n")


def summarize(text, cfg, chat=llm.chat, log=print, background="", notes_out=None):
    """Return the update body (the three sections). Long transcripts are noted part by part, then merged.
    background = project context and known terms (and the previous update); notes_out = a path to keep the minutes."""
    if not text.strip():
        raise SummaryError("the transcript is empty: nothing to summarize")
    lang = cfg.get("output_language") or "English"
    ctx = background_block(background)
    limit = int(cfg.get("max_input_chars") or 12000)
    material, rounds = text, 0
    # minutes per part; if the joined minutes are still too long (a very long meeting), take minutes of the minutes.
    # English minutes cost fewer tokens per character than most transcripts (Bangla script costs 2 to 3 times
    # more), so they may be twice as long before another round
    while len(material) > (limit if rounds == 0 else 2 * limit) and rounds < 3:
        rounds += 1
        parts = split(material, limit)
        notes = []
        for i, part in enumerate(parts, 1):
            log(f"notes, round {rounds}: part {i}/{len(parts)}")
            sys_msg = prompt("notes", part=i, parts=len(parts), output_language=lang, context=ctx)
            notes.append(f"## Part {i} of {len(parts)}\n\n" + clean_reply(chat(cfg, [
                {"role": "system", "content": sys_msg}, {"role": "user", "content": part}])))
        material = "\n\n".join(notes)
        if notes_out:
            Path(notes_out).write_text(material + "\n", encoding="utf-8")
            log(f"minutes kept in {notes_out}")
    material = ("Minutes taken from each part of the meeting, in order:\n\n" if rounds else "Transcript:\n\n") + material
    messages = [{"role": "system", "content": prompt("update", output_language=lang, context=ctx)},
                {"role": "user", "content": material}]
    log("writing the update")
    reply = chat(cfg, messages)
    body = clean_reply(reply)
    gaps = missing(body)
    if gaps:
        log(f"the reply missed {', '.join(gaps)}: asking once more")
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": f"Your answer is missing these headings: {', '.join(gaps)}. "
                                                 "Return the whole update again, with all three sections."}]
        reply = chat(cfg, messages)
        body = clean_reply(reply)
        gaps = missing(body)
        if gaps:
            raise SummaryError(f"the model's reply still misses {', '.join(gaps)}", reply)
    return body
