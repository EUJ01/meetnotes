"""Copy update files to a folder (Google Drive for desktop, OneDrive, Dropbox, Syncthing) or an rclone remote."""
import os
import shutil
import subprocess
from pathlib import Path

from meetnotes.publish import PublishError


class Folder:
    name = "folder"

    def __init__(self, root):
        self.root = Path(root).expanduser()

    def wants(self, project):
        return True

    def send(self, path, project, date, previous):
        # the root must exist: an unmounted drive must give an error, not a new folder on the wrong disk
        if not self.root.is_dir():
            raise PublishError(f"folder {self.root} does not exist (is the drive mounted?)")
        dest = self.root / project
        dest.mkdir(exist_ok=True)
        tmp = dest / f".{path.name}.part"  # copy, then rename: a sync client never uploads half a file
        shutil.copyfile(path, tmp)
        os.replace(tmp, dest / path.name)
        return "", "copied"


class Rclone:
    name = "rclone"

    def __init__(self, remote):
        self.remote = remote.rstrip("/")

    def wants(self, project):
        return True

    def send(self, path, project, date, previous):
        exe = shutil.which("rclone")
        if not exe:
            raise PublishError("rclone is not on PATH (https://rclone.org/install/)")
        done = subprocess.run([exe, "copyto", str(path), f"{self.remote}/{project}/{path.name}"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode:
            raise PublishError(f"rclone failed: {done.stderr.strip()[-300:]}")
        return "", "copied"
