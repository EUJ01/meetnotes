"""meetnotes command line. Progress goes to stderr, results (file paths) to stdout.
Exit codes: 0 ok, 1 a step failed, 2 usage or config error."""
import argparse
import datetime as dt
import os
import platform
import shutil
import sys
import traceback
from pathlib import Path

from meetnotes import Fail, __version__, config, device, transcript, update


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------- steps ----------

def do_transcribe(media, cfg, ws, out=None, language=None, model=None, dev=None, batch=None, seconds=0, force=False):
    from meetnotes import asr, audio
    media = Path(media).resolve()
    if not media.is_file():
        raise Fail(f"recording not found: {media}", 2)
    size, limit = media.stat().st_size, int(seconds or 0)
    if batch is not None and batch < 1:
        raise Fail("--batch must be 1 or more", 2)
    # a test run on the first N seconds gets its own file, so the full run after it does not collide
    out = Path(out) if out else ws / "transcripts" / (f"{media.stem}.first{limit}s.md" if limit else f"{media.stem}.md")
    if out.exists() and not force:
        meta, _ = transcript.read(out)
        same = (meta.get("source_path"), meta.get("size"), meta.get("limit", "0")) == (str(media), str(size), str(limit))
        asked = (language and language != meta.get("language")) or (model and model != meta.get("model"))
        if same and not asked:
            log(f"transcript exists, skipped (--force redoes it): {out}")
            return out
        why = "was made with another language or model" if same else "belongs to another recording or length"
        raise Fail(f"{out} {why}. Use --force to replace it, or --out for a new file.", 2)
    t = cfg["transcribe"]
    lang, used, text = asr.transcribe(
        media, language=language or t["language"], override=model, whisper_model=t["model"], bn_model=t["model_bn"],
        device=dev or t["device"], batch=int(batch or t["batch"]), seconds=limit, log=log)
    if not text:
        log("warning: no speech found")
    length = audio.duration(media)
    meta = {"source": media.name, "source_path": str(media), "size": size,
            "recorded": dt.date.fromtimestamp(media.stat().st_mtime).isoformat(),
            "duration": round(min(length, limit) if limit else length, 1), "limit": limit, "language": lang, "model": used}
    transcript.write(out, meta, text)
    log(f"{len(text.split()):,} words")
    return out


def do_clean(path, cfg, report=False):
    from meetnotes import glossary
    gpath = cfg["clean"]["glossary"]
    if not gpath:
        raise Fail("no glossary configured: set [clean] glossary in config.toml (see glossary.example.json)", 2)
    path = Path(path)
    meta, text = transcript.read(path)
    if meta.get("language") not in (None, "bn"):
        log(f"warning: the glossary step is made for Bangla; this transcript is '{meta['language']}'")
    g = glossary.load(gpath)
    clean, hits, dropped = glossary.clean(text, g)
    out = path.with_name(path.stem + ".clean.md")
    transcript.write(out, meta, clean)
    if report:
        rep = path.with_name(path.stem + ".glossary.md")
        rep.write_text(glossary.report(meta.get("source", path.name), text, hits, dropped, g, gpath), encoding="utf-8")
        log(f"report: {rep}")
    log(f"{dropped} noise spans, {sum(map(len, hits.values()))} glossary entries used")
    return out


def _date(given, meta):
    if given:
        return update.parse_date(given)
    if meta.get("recorded"):
        log(f"date: {meta['recorded']} (the recording's file date; pass --date if that is wrong)")
        return update.parse_date(meta["recorded"])
    raise Fail("no date: pass --date YYYY-MM-DD", 2)


def _target(path, project, date, ws):
    meta, text = transcript.read(path)
    meta.setdefault("source", Path(path).name)
    date = _date(date, meta)
    return meta, text, date, update.path_for(ws / "projects", project, date, update.source_id(meta))


def _wants_translation(llm_cfg, meta):
    """auto: translate when the transcript is in a known language other than English and the output is English."""
    t = llm_cfg.get("translate", "auto")
    if t in (True, False):
        return t
    out = (llm_cfg.get("output_language") or "English").strip().lower()
    return meta.get("language") not in (None, "", "en", "unknown") and out in ("english", "en")


def _translated(path, meta, text, cfg, background):
    """The translation, cached next to the transcript as <name>.translated.md. It is reused while the transcript
    text, the LLM model and the project background (context, terms) are the same."""
    import hashlib
    from meetnotes import summarize
    digest = hashlib.sha256((text + "\0" + background).encode("utf-8")).hexdigest()[:16]
    cache = Path(path).with_name(Path(path).stem + ".translated.md")
    if cache.exists():
        old, english = transcript.read(cache)
        if old.get("translated_from") == digest and old.get("translated_by") == cfg["llm"]["model"]:
            log(f"using the saved translation: {cache}")
            return english
    english = summarize.translate(text, cfg["llm"], log=log, background=background)
    transcript.write(cache, {**meta, "translated_from": digest, "translated_by": cfg["llm"]["model"]}, english)
    log(f"translation saved: {cache}")
    return english


def do_summarize(path, project, cfg, ws, date=None):
    from meetnotes import summarize
    meta, text, date, dest = _target(path, project, date, ws)
    proj = cfg["projects"].get(project, {})
    background = proj.get("context", "")
    if proj.get("terms"):
        background += "\nTerms that come up in this project (the speech model often mishears them): " + ", ".join(proj["terms"])
    prev = update.previous(ws / "projects", project, date)
    if prev:
        background += "\nThe previous update of this project, for context only:\n" + prev
    try:
        work = _translated(path, meta, text, cfg, background) if _wants_translation(cfg["llm"], meta) else text
        minutes = dest.with_name(dest.name[:-3] + ".minutes.md")
        minutes.unlink(missing_ok=True)  # a stale file from an earlier run must not reach the review
        body = summarize.summarize(work, cfg["llm"], log=log, background=background, notes_out=minutes)
        if cfg["llm"]["review"]:
            from meetnotes import agent
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.with_name(dest.name[:-3] + ".draft.md").write_text(body + "\n", encoding="utf-8")
            body = agent.review(body, work, cfg["llm"], background=background, log=log,
                                minutes=minutes.read_text(encoding="utf-8") if minutes.exists() else "")
    except summarize.SummaryError as e:
        if e.reply:
            failed = dest.with_name(dest.name + ".failed.md")
            failed.parent.mkdir(parents=True, exist_ok=True)
            failed.write_text(e.reply, encoding="utf-8")
            log(f"the raw reply is in {failed}")
        raise
    update.write(dest, update.header(project, date, meta, len(text.split()), cfg["llm"]["model"]) + body)
    return dest


def do_new_update(path, project, ws, date=None):
    meta, text, date, dest = _target(path, project, date, ws)
    if dest.exists():
        log(f"the update file exists already; edit it: {dest}")
        return dest
    update.write(dest, update.header(project, date, meta, len(text.split()), "an agent") + update.skeleton())
    return dest


def do_publish(cfg, ws, project=None, dry_run=False):
    from meetnotes import publish
    if project:
        update.check_project(project)
    return 1 if publish.publish(cfg["publish"], ws, project, dry_run, log=log) else 0


def list_chats(cfg):
    from meetnotes.publish.telegram import Telegram
    env = cfg["publish"]["telegram"]["token_env"]
    if not os.environ.get(env):
        raise Fail(f"set the bot token in the environment variable {env} first", 2)
    chats = Telegram(os.environ[env], {}).list_chats()
    if not chats:
        log("no chats in the bot's recent updates: post a message in the chat, then run this again")
    for cid, (kind, title) in chats.items():
        print(f"{cid}\t{kind}\t{title}")


def doctor(cfg, ws):
    bad = 0

    def line(ok, what, fix=""):
        nonlocal bad
        bad += not ok
        print(f"[{'ok' if ok else '!!'}] {what}" + (f"\n      fix: {fix}" if fix and not ok else ""))

    line(sys.version_info >= (3, 11), f"Python {platform.python_version()}", "use Python 3.11 or newer")
    for tool in ("ffmpeg", "ffprobe"):
        from meetnotes.audio import INSTALL
        line(bool(shutil.which(tool)), f"{tool} on PATH", INSTALL)
    try:
        import torch
        where = device.pick(torch, "auto")
        gpu_seen = bool(shutil.which("nvidia-smi") or shutil.which("rocm-smi") or shutil.which("hipinfo"))
        cpu_only = device.build(torch) == "CPU-only" and where == "cpu"
        line(not (cpu_only and gpu_seen), f"PyTorch {torch.__version__} ({device.build(torch)}), device: {where}",
             "this machine has a GPU but PyTorch is a CPU-only build: reinstall it from pytorch.org (see README)")
    except ImportError:
        line(False, "PyTorch", "install PyTorch for your GPU (see README), then: pip install .[asr]")
    for mod in ("transformers", "soundfile", "librosa", "numpy"):
        try:
            m = __import__(mod)
            line(True, f"{mod} {getattr(m, '__version__', '')}")
        except ImportError:
            line(False, mod, "pip install .[asr]")
    if cfg["_file"]:
        print(f"[ok] config: {cfg['_file']}; workspace: {ws}")
    else:
        print(f"[--] no config.toml: defaults (transcription only); workspace: {ws}. "
              "Copy config.example.toml to config.toml to add an LLM or publishing.")
    llm_cfg = cfg["llm"]
    if llm_cfg["base_url"]:
        from meetnotes import llm
        try:
            ids = llm.models(llm_cfg)
            known = llm_cfg["model"] in ids or not ids
            line(known, f"LLM at {llm_cfg['base_url']}: {len(ids)} models listed",
                 f"model '{llm_cfg['model']}' is not in the list: {', '.join(ids[:8])}")
        except Fail as e:
            line(False, f"LLM: {e}", "start the server, or fix [llm] base_url")
        if llm_cfg["api_key_env"]:
            line(bool(os.environ.get(llm_cfg["api_key_env"])), f"API key in ${llm_cfg['api_key_env']}",
                 f"set the environment variable {llm_cfg['api_key_env']}")
    else:
        print("[--] no LLM configured: use the agent route (AGENTS.md) or set [llm] in config.toml")
    tg = cfg["publish"]["telegram"]
    if tg["chats"]:
        line(bool(os.environ.get(tg["token_env"])), f"Telegram token in ${tg['token_env']}", f"set {tg['token_env']}")
    if cfg["publish"]["folder"]["path"]:
        p = Path(cfg["publish"]["folder"]["path"]).expanduser()
        line(p.is_dir(), f"publish folder {p}", "create it, or mount the drive")
    if cfg["publish"]["rclone"]["remote"]:
        line(bool(shutil.which("rclone")), "rclone on PATH", "https://rclone.org/install/")
    return 1 if bad else 0


# ---------- command line ----------

def build_parser():
    p = argparse.ArgumentParser(prog="meetnotes", description="Meeting recording -> transcript -> to-do update file.")
    p.add_argument("--version", action="version", version=f"meetnotes {__version__}")
    p.add_argument("--config", help="config file (default: ./config.toml)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def asr_args(s):
        s.add_argument("--language", help="auto (default), or a code such as en, de, bn")
        s.add_argument("--model", help="a Hugging Face model id; overrides the config")
        s.add_argument("--device", help="auto, cuda (NVIDIA and AMD ROCm), mps or cpu")
        s.add_argument("--batch", type=int, help="chunks per GPU batch (default 8; halves itself on out-of-memory)")
        s.add_argument("--seconds", type=int, default=0, help="transcribe only the first N seconds (for a test)")
        s.add_argument("--force", action="store_true", help="redo the transcript even if it exists")

    sub.add_parser("doctor", help="check the setup")
    s = sub.add_parser("transcribe", help="recording -> transcripts/<name>.md")
    s.add_argument("media")
    s.add_argument("--out", help="transcript path (default: <workspace>/transcripts/<name>.md)")
    asr_args(s)
    s = sub.add_parser("clean", help="apply the Bangla glossary -> <name>.clean.md")
    s.add_argument("transcript")
    s.add_argument("--report", action="store_true", help="also write <name>.glossary.md")
    for name, helptext in (("summarize", "transcript -> update file, with the configured LLM"),
                           ("new-update", "create an empty update file for an agent to fill in; prints its path")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("transcript")
        s.add_argument("--project", required=True)
        s.add_argument("--date", help="meeting date YYYY-MM-DD (default: the recording's file date)")
    s = sub.add_parser("publish", help="send new or changed update files to Telegram / a folder / rclone")
    s.add_argument("--project")
    s.add_argument("--dry-run", action="store_true", help="list what would be sent")
    s.add_argument("--list-chats", action="store_true",
                   help="show chat ids the bot saw in the last day (post in the chat first; fails while a webhook is set)")
    s = sub.add_parser("run", help="transcribe, clean, summarize and publish in one go")
    s.add_argument("media")
    s.add_argument("--project", required=True)
    s.add_argument("--date", help="meeting date YYYY-MM-DD (default: the recording's file date)")
    asr_args(s)
    return p


def dispatch(a, cfg, ws):
    if a.cmd == "doctor":
        return doctor(cfg, ws)
    if a.cmd == "transcribe":
        print(do_transcribe(a.media, cfg, ws, a.out, a.language, a.model, a.device, a.batch, a.seconds, a.force))
    elif a.cmd == "clean":
        print(do_clean(a.transcript, cfg, a.report))
    elif a.cmd == "summarize":
        print(do_summarize(a.transcript, update.check_project(a.project), cfg, ws, a.date))
    elif a.cmd == "new-update":
        print(do_new_update(a.transcript, update.check_project(a.project), ws, a.date))
    elif a.cmd == "publish":
        if a.list_chats:
            list_chats(cfg)
            return 0
        return do_publish(cfg, ws, a.project, a.dry_run)
    elif a.cmd == "run":
        project = preflight(a, cfg)
        path = do_transcribe(a.media, cfg, ws, None, a.language, a.model, a.device, a.batch, a.seconds, a.force)
        print(path)
        if cfg["clean"]["glossary"] and transcript.read(path)[0].get("language") == "bn":
            path = do_clean(path, cfg)
            print(path)
        if not cfg["llm"]["base_url"]:
            log(f"no LLM configured: stopping after the transcript. Agent route: meetnotes new-update {path} --project {project}")
            return 0
        print(do_summarize(path, project, cfg, ws, a.date))
        if a.seconds:
            log("--seconds is a test run: not published. Publish it by hand with: meetnotes publish")
            return 0
        return do_publish(cfg, ws, project)
    return 0


def preflight(a, cfg):
    """Settings errors that would otherwise show up only after an hour of transcription."""
    project = update.check_project(a.project)
    if a.date:
        update.parse_date(a.date)
    if cfg["llm"]["base_url"] and not cfg["llm"]["model"]:
        raise Fail("[llm] base_url is set but model is empty", 2)
    g = cfg["clean"]["glossary"]
    if g and not Path(g).is_file():
        raise Fail(f"[clean] glossary file not found: {g}", 2)
    from meetnotes import publish
    for t in publish.targets(cfg["publish"]):
        if isinstance(t, publish.Unavailable):
            log(f"warning: {t.name} will fail: {t.reason}")
    return project


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Bangla text on a Windows cp1252 console would raise UnicodeEncodeError
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        cfg, ws = config.load(args.config)
        code = dispatch(args, cfg, ws) or 0
    except Fail as e:
        log(f"error: {e}")
        code = e.code
    except KeyboardInterrupt:
        log("stopped")
        code = 130
    except Exception:
        traceback.print_exc()
        code = 1
    device.hard_exit(code)  # Windows + ROCm only; otherwise a normal return
    return code


def entry():
    sys.exit(main())
