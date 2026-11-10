"""Clean a Bangla transcript with a glossary file: drop noise, fix misrecognitions, turn Banglish into English.

Glossary format (see glossary.example.json), applied in this order, longest key first:
  drop      regexes for noise spans -> [unclear]
  fixes     sure corrections
  guesses   corrections inferred from context, listed apart in the report so they can be rejected
  terms     Bangla-script spelling of an English term -> English; a Bangla ending stays: ওয়ার্ডগুলো -> words-গুলো
  doubtful  phrases to list in the report, unchanged
The word boundaries are Bangla letters, so this step is only useful for Bangla transcripts.
"""
import json
import re
from pathlib import Path

from meetnotes import Fail

BN = "ঀ-৿"
# Bangla endings that stay Bangla after the English word (ওয়ার্ডগুলো -> words-গুলো); longest first
SUFFIXES = sorted("গুলোকে গুলোর গুলো গুলি গুলা টাকে টাও টার টাই টা টি য়ের ের ে এর র কে তে রা দের য় ও ই".split(), key=len, reverse=True)
SUFFIX_FORM = {"ের": "এর", "য়ের": "এর", "ে": "এ"}  # vowel signs need a letter to stand alone after a hyphen
PARTS = ("fixes", "guesses", "terms")


def load(path):
    try:
        g = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise Fail(f"glossary {path}: {e}", 2)
    for key in ("drop", "doubtful"):
        g.setdefault(key, [])
    for key in PARTS:
        g.setdefault(key, {})
    return g


def key_regex(key):
    body = r"\s+".join(re.escape(p) for p in key.split())
    return re.compile(rf"(?<![{BN}]){body}(?:-?({'|'.join(SUFFIXES)}))?(?![{BN}])")


def apply_map(text, mapping, hits):
    """Replace every key (longest first, whole words only, optional Bangla ending). hits collects {key: count}."""
    for key in sorted(mapping, key=len, reverse=True):
        def sub(m, key=key):
            hits[key] = hits.get(key, 0) + 1
            end = m.group(1)
            return mapping[key] + (f"-{SUFFIX_FORM.get(end, end)}" if end else "")
        text = key_regex(key).sub(sub, text)
    return text


def normalize(text):
    return re.sub(rf"\s+-(?=[{BN}])", "-", text)  # the model writes "ওয়ার্ড -গুলো"


def clean(text, g):
    """Return (clean text, hits per part, number of dropped noise spans)."""
    text = normalize(text)
    dropped = 0
    for pat in g["drop"]:
        text, n = re.subn(pat, " [unclear] ", text, flags=re.S)
        dropped += n
    hits = {part: {} for part in PARTS}
    for part in PARTS:
        text = apply_map(text, g[part], hits[part])
    text = re.sub(rf"(?<=[A-Za-z]) (গুলো|গুলি|গুলা|টা|টি|এর)(?![{BN}])", r"-\1", text)  # "words গুলো" -> "words-গুলো"
    return re.sub(r"\s{2,}", " ", text).strip(), hits, dropped


def context(text, snippet, width=7, at=None):
    i = text.find(snippet) if at is None else at
    if i < 0:
        return None
    before, after = text[:i].split()[-width:], text[i + len(snippet):].split()[:width]
    return " ".join(before) + " **" + snippet + "** " + " ".join(after)


def report(name, raw, hits, dropped, g, glossary_path):
    raw = normalize(raw)
    lines = [f"# Glossary report: {name}", "",
             f"{dropped} stretches of noise replaced by `[unclear]`. Every entry below can be edited in `{glossary_path}`; "
             "run `meetnotes clean` again after a change.", "",
             "## Guesses (inferred from context, please check)", "",
             "| Heard | Replaced by | Times | First context (in the raw text) |", "|---|---|---|---|"]
    for k, n in sorted(hits["guesses"].items(), key=lambda kv: -kv[1]):
        m = key_regex(k).search(raw)
        lines.append(f"| {k} | {g['guesses'][k]} | {n} | {context(raw, m.group(0), at=m.start()) if m else ''} |")
    lines += ["", "## Still doubtful (not changed)", ""]
    lines += [f"- {c}" for c in (context(raw, s) for s in g["doubtful"]) if c]
    lines += ["", "## Sure fixes", "", "| Heard | Replaced by | Times |", "|---|---|---|"]
    lines += [f"| {k} | {g['fixes'][k]} | {n} |" for k, n in sorted(hits["fixes"].items(), key=lambda kv: -kv[1])]
    lines += ["", "## Terms: Banglish to English", "", "| Banglish | English | Times |", "|---|---|---|"]
    lines += [f"| {k} | {g['terms'][k]} | {n} |" for k, n in sorted(hits["terms"].items(), key=lambda kv: -kv[1])]
    unused = [k for k in g["terms"] if k not in hits["terms"]]
    lines += ["", f"Terms that matched nothing ({len(unused)}): " + ", ".join(unused), ""]
    return "\n".join(lines)
