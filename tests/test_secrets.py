"""No tracked file may hold a Telegram bot token or a real-looking Telegram chat id."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
PATTERNS = {
    "bot token": re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),
    "chat id": re.compile(r"-100\d{10,}"),
    "API key": re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,})"),
}
SKIP = {".git", "__pycache__", ".venv", "venv", "build", "dist"}


def files():
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split("\n")
        return [ROOT / f for f in out if f]
    except (OSError, subprocess.CalledProcessError):  # not a git checkout: scan everything
        return [p for p in ROOT.rglob("*") if p.is_file() and not SKIP & set(p.relative_to(ROOT).parts)]


class NoSecrets(unittest.TestCase):
    def test_tracked_files(self):
        for path in files():
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, pat in PATTERNS.items():
                m = pat.search(text)
                self.assertIsNone(m, f"{name} in {path.relative_to(ROOT)}: {m and m.group(0)[:12]}...")


if __name__ == "__main__":
    unittest.main()
