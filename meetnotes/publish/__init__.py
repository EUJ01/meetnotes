"""Send new or changed update files to every configured target. The ledger (.meetnotes/ledger.tsv) keeps one row
per file and target: path, sha256, target, message id. Each target catches up on its own, so one failing target
never blocks another. Deleting a local file does not delete the remote copy."""
import hashlib
import os
from pathlib import Path

from meetnotes import Fail


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

    def get(self, rel, target):
        return self.rows.get((rel, target))

    def set(self, rel, target, digest, msg_id):
        self.rows[(rel, target)] = (digest, msg_id or "")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text("".join(f"{r}\t{d}\t{t}\t{m}\n" for (r, t), (d, m) in sorted(self.rows.items())), encoding="utf-8")
        os.replace(tmp, self.path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def update_files(projects_dir, project=None):
    """Oldest first: the names start with an inverted date, so descending name order is ascending date order."""
    pattern = f"{project}/*_update.md" if project else "*/*_update.md"
    return sorted(Path(projects_dir).glob(pattern), key=lambda p: p.name, reverse=True)


def targets(cfg):
    """The configured targets, in order: telegram, folder, rclone."""
    from meetnotes.publish import folder, telegram
    out = []
    t = cfg["telegram"]
    if t.get("chats") and os.environ.get(t.get("token_env") or ""):
        out.append(telegram.Telegram(os.environ[t["token_env"]], t["chats"]))
    elif t.get("chats"):
        raise PublishError(f"Telegram chats are set but the environment variable {t.get('token_env')} is empty", 2)
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
        digest = sha256(f)
        for t in tlist:
            old = ledger.get(rel, t.name)
            if old and old[0] == digest:
                continue
            if not t.wants(proj):
                if (t.name, proj) not in skipped:
                    skipped.add((t.name, proj))
                    log(f"{t.name}: no chat id for project '{proj}' in the config, skipped")
                continue
            if dry_run:
                log(f"would {'update' if old else 'send'} {rel} -> {t.name}")
                continue
            try:
                msg_id, did = t.send(f, proj, date, old[1] if old else "")
            except PublishError as e:
                log(f"{t.name}: {rel}: {e}")
                failed += 1
                continue
            ledger.set(rel, t.name, digest, msg_id)
            log(f"{t.name}: {did} {rel}")
            sent += 1
    if not sent and not failed and not dry_run:
        log("publish: nothing new to send")
    return failed
