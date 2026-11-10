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
    out = Path(out) if out else ws / "transcripts" / f"{media.stem}.md"
    size, limit = media.stat().st_size, int(seconds or 0)
    if out.exists() and not force:
        meta, _ = transcript.read(out)
        if (meta.get("source_path"), meta.get("size"), meta.get("limit", "0")) == (str(media), str(size), str(limit)):
            log(f"transcript exists, skipped (--force redoes it): {out}")
            return out
        raise Fail(f"{out} belongs to another recording or length. Use --out for a new file, or --force to replace it.", 2)
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
    return meta, text, date, update.path_for(ws / "projects", project, date, meta["source"])


def do_summarize(path, project, cfg, ws, date=None):
    from meetnotes import summarize
    meta, text, date, dest = _target(path, project, date, ws)
    try:
        body = summarize.summarize(text, cfg["llm"], log=log)
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
    try:
        import transformers
        line(True, f"transformers {transformers.__version__}")
    except ImportError:
        line(False, "transformers", "pip install .[asr]")
    line(bool(cfg["_file"]), f"config: {cfg['_file'] or 'none (defaults)'}; workspace: {ws}",
         "copy config.example.toml to config.toml and edit it")
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
        project = update.check_project(a.project)
        if a.date:
            update.parse_date(a.date)  # fail now, not after an hour of transcription
        path = do_transcribe(a.media, cfg, ws, None, a.language, a.model, a.device, a.batch, a.seconds, a.force)
        print(path)
        if cfg["clean"]["glossary"] and transcript.read(path)[0].get("language") == "bn":
            path = do_clean(path, cfg)
            print(path)
        if not cfg["llm"]["base_url"]:
            log(f"no LLM configured: stopping after the transcript. Agent route: meetnotes new-update {path} --project {project}")
            return 0
        print(do_summarize(path, project, cfg, ws, a.date))
        return do_publish(cfg, ws, project)
    return 0


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
