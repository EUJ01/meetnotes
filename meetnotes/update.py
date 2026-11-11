"""Update files: projects/<project>/<key>_<YYYY-MM-DD>[_<n>]_update.md, where key = 99999999 minus the date as
YYYYMMDD, so the newest update sorts first in any file list."""
import datetime as dt
import re
from pathlib import Path

from meetnotes import Fail
from meetnotes.summarize import HEADINGS
from meetnotes.transcript import save

PROJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SOURCE = re.compile(r"^<!-- meetnotes source: (.*) -->$", re.M)  # file name + size: names like zoom_0.mp4 repeat


def source_id(meta):
    return f"{meta.get('source', 'unknown')} {meta.get('size', '')}".strip()


def check_project(name):
    if not name or not PROJECT.match(name) or ".." in name:
        raise Fail(f"project name '{name}': use letters, digits, '.', '_' or '-' (no spaces or slashes)", 2)
    return name


def parse_date(text):
    try:
        return dt.date.fromisoformat(text)
    except (TypeError, ValueError):
        raise Fail(f"date '{text}': use YYYY-MM-DD", 2)


def key(date):
    return f"{99999999 - int(date.strftime('%Y%m%d')):08d}"


def path_for(projects_dir, project, date, source):
    """The file for this meeting. source = source_id(meta). Same date and same source: the same path (it is
    replaced, then published as an edit). Same date, another source: a numbered file, _2_ before _update so the publish pattern still matches
    and it sorts above the first one. # ponytail: _10_ sorts above _2_; fine below 10 meetings a day."""
    folder = Path(projects_dir) / check_project(project)
    base = f"{key(date)}_{date.isoformat()}"
    n = 1
    while True:
        p = folder / (f"{base}_update.md" if n == 1 else f"{base}_{n}_update.md")
        if not p.exists():
            return p
        m = SOURCE.search(p.read_text(encoding="utf-8"))
        if m and m[1] == source:
            return p
        n += 1


def header(project, date, meta, words, summarizer):
    """The facts the LLM must not state: written by code. Only the file name of the source goes out, never its path."""
    minutes = f"{float(meta['duration']) / 60:.0f} min, " if meta.get("duration") else ""
    lang = f"{meta['language']}, " if meta.get("language") else ""
    asr = f" Transcribed with {meta['model']}." if meta.get("model") else ""
    return (f"# {project} update: {date.isoformat()}\n\n"
            f"Source: `{meta.get('source', 'unknown')}` ({minutes}{lang}{words:,} words).{asr} Summary by {summarizer}. "
            "Machine transcript: check important points against the recording.\n"
            f"<!-- meetnotes source: {source_id(meta)} -->\n\n")


def skeleton():
    return "\n\n".join(f"{h}\n\n" for h in HEADINGS).rstrip() + "\n"


def write(path, text):
    save(path, text.rstrip() + "\n")


def previous(projects_dir, project, date, limit=6000):
    """The body of the latest update before this date, as context for the next one ('' if none)."""
    older = [p for p in (Path(projects_dir) / project).glob("*_update.md") if p.name.split("_")[1] < date.isoformat()]
    if not older:
        return ""
    last = min(older, key=lambda p: p.name)  # the smallest key is the newest date
    body = last.read_text(encoding="utf-8").split("## Summary", 1)
    return ("## Summary" + body[1])[:limit].strip() if len(body) == 2 else ""
