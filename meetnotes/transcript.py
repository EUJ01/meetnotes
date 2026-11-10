"""A transcript file: a small front matter block (where the text came from) and the text.

---
source: recording.mp4
source_path: /full/path/recording.mp4
size: 123456
recorded: 2026-10-20
duration: 1560.3
limit: 0
language: bn
model: SayedShaun/Qwen3-ASR-0.6B-Bengali
---
the transcript text ...
"""
import os
from pathlib import Path

FIELDS = ["source", "source_path", "size", "recorded", "duration", "limit", "language", "model"]


def write(path, meta, text):
    """Write atomically, so a crash never leaves half a transcript that looks complete."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "".join(f"{k}: {meta[k]}\n" for k in FIELDS if k in meta)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(f"---\n{head}---\n{text.strip()}\n", encoding="utf-8")
    os.replace(tmp, path)


def read(path):
    """Return (meta dict, text). A file without front matter is all text (a transcript from elsewhere)."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in (l.strip() for l in lines[1:]):
        return {}, raw.strip()
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    meta = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(": ")  # values may contain ':' (Windows paths), the key never does
        if sep:
            meta[key.strip()] = value.strip()
    return meta, "\n".join(lines[end + 1:]).strip()
