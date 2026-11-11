"""Send new or changed update files to every configured target. The ledger (.meetnotes/ledger.tsv) keeps one row
per file and destination: path, sha256, destination, message id. The destination includes the folder, remote or
chat id, so a changed setting sends the files to the new place. Each destination catches up on its own: one failing
target never blocks another. Deleting a local file does not delete the remote copy."""
import hashlib
import os
from pathlib import Path

from meetnotes import Fail
from meetnotes.transcript import save


class PublishError(Fail):
    pass


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                f = line.split("\t")
                if len(f) == 4:
                    self.rows[(f[0], f[2])] = (f[1], f[3])

    def get(self, rel, dest):
        return self.rows.get((rel, dest))

    def set(self, rel, dest, digest, msg_id):
        self.rows[(rel, dest)] = (digest, msg_id or "")
        save(self.path, "".join(f"{r}\t{d}\t{t}\t{m}\n" for (r, t), (d, m) in sorted(self.rows.items())))


class Unavailable:
    """A configured target that cannot work (for example no token): every send fails, the others still run."""

    def __init__(self, name, reason):
        self.name, self.reason = name, reason

    def wants(self, project):
        return True

    def dest(self, project):
        return self.name

    def send(self, *a):
        raise PublishError(self.reason)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def update_files(projects_dir, project=None):
    """Oldest first: the names start with an inverted date, so descending name order is ascending date order."""
    pattern = f"{project}/*_update.md" if project else "*/*_update.md"
    return sorted(Path(projects_dir).glob(pattern), key=lambda p: p.name, reverse=True)


def is_empty(text):
    """An update made by new-update that nobody filled in yet: only the header, headings and blank lines."""
    body = text.split("## Summary", 1)[-1]
    return not any(line.strip() and not line.startswith("#") for line in body.splitlines())


def targets(cfg):
    """The configured targets, in order: telegram, folder, rclone."""
    from meetnotes.publish import folder, telegram
    out = []
    t = cfg["telegram"]
    if t.get("chats"):
        token = os.environ.get(t.get("token_env") or "", "").strip()
        out.append(telegram.Telegram(token, t["chats"]) if token else
                   Unavailable("telegram", f"the environment variable {t.get('token_env')} (the bot token) is empty"))
    if cfg["folder"].get("path"):
        out.append(folder.Folder(cfg["folder"]["path"]))
    if cfg["rclone"].get("remote"):
        out.append(folder.Rclone(cfg["rclone"]["remote"]))
    return out


def publish(cfg, workspace, project=None, dry_run=False, log=print, chosen=None):
    """Return the number of failed sends. chosen = a list of targets (tests); default = from the config."""
    tlist = targets(cfg) if chosen is None else chosen
    if not tlist:
        log("publish: no target configured ([publish.telegram], [publish.folder] or [publish.rclone])")
        return 0
    projects = Path(workspace) / "projects"
    ledger = Ledger(Path(workspace) / ".meetnotes" / "ledger.tsv")
    failed, sent, skipped = 0, 0, set()
    for f in update_files(projects, project):
        rel = f.relative_to(projects).as_posix()
        proj, date = f.parent.name, f.name.split("_")[1]
        if is_empty(f.read_text(encoding="utf-8")):
            log(f"skipped {rel}: its sections are still empty")
            continue
        digest = sha256(f)
        for t in tlist:
            if not t.wants(proj):
                if (t.name, proj) not in skipped:
                    skipped.add((t.name, proj))
                    log(f"{t.name}: no chat id for project '{proj}' in the config, skipped")
                continue
            dest = t.dest(proj)
            old = ledger.get(rel, dest)
            if old and old[0] == digest:
                continue
            if dry_run:
                log(f"would {'update' if old else 'send'} {rel} -> {dest}")
                continue
            try:
                msg_id, did = t.send(f, proj, date, old[1] if old else "")
            except (PublishError, OSError, ValueError) as e:  # a disk, permission or protocol error: count it, go on
                log(f"{t.name}: {rel}: {e}")
                failed += 1
                continue
            ledger.set(rel, dest, digest, msg_id)
            log(f"{t.name}: {did} {rel}")
            sent += 1
    if not sent and not failed and not dry_run:
        log("publish: nothing new to send")
    return failed
