"""ffmpeg helpers: length, pauses, and cutting a recording into <= 20 s 16 kHz mono wav chunks."""
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from meetnotes import Fail

MIN_CHUNK = 8  # seconds; a pause earlier than this is not worth a cut
INSTALL = "Install ffmpeg: Windows `winget install Gyan.FFmpeg`, macOS `brew install ffmpeg`, Linux `sudo apt install ffmpeg`."


def need_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise Fail(f"{tool} is not on PATH. {INSTALL} Then open a new terminal.")


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def duration(media):
    """Length in seconds, from ffprobe. Raises Fail when the file has no audio stream."""
    probe = _run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(media)])
    if probe.returncode or not probe.stdout.strip():
        raise Fail(f"no audio stream found in {media}")
    fmt = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(media)])
    try:
        return float(fmt.stdout.strip())
    except ValueError:
        raise Fail(f"ffprobe could not read the length of {media}")


def cut_points(pauses, total, chunk, min_chunk=MIN_CHUNK):
    """Cut times: the latest pause between min_chunk and chunk seconds after the previous cut, else a hard cut.
    pauses = mid-points of the silences, in seconds. A clip of `chunk` seconds or less gets no cut."""
    pos, cuts = 0.0, []
    while pos + chunk < total:
        near = [t for t in pauses if pos + min_chunk < t <= pos + chunk]
        pos = max(near) if near else pos + chunk
        cuts.append(round(pos, 2))
    return cuts


def _levels(media, seconds):
    """(mean volume in dB, pause mid-points). # ponytail: ffmpeg silencedetect, not a speech VAD; steady background
    music or noise can hide the pauses and fall back to hard cuts. Swap in silero-vad if that shows up."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media)] + (["-t", str(seconds)] if seconds else [])
    found = re.search(r"mean_volume: (-?[\d.]+|-inf)", _run(cmd + ["-af", "volumedetect", "-f", "null", "-"]).stderr)
    if not found or found[1] == "-inf":
        return -91.0, []  # digital silence: no pauses to find
    mean = float(found[1])
    # pause = 6 dB below the average level (a fixed -35 dB found no pauses in loud audio), 0.12 s or longer
    err = _run(cmd + ["-af", f"silencedetect=noise={mean - 6}dB:d=0.12", "-f", "null", "-"]).stderr
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: (-?[\d.]+)", err)]
    return mean, [(s + e) / 2 for s, e in zip(starts, ends)]


def is_quiet(chunk_db, file_db, margin=25.0):
    """A chunk far below the file's average level is silence. Whisper invents text on silence ("Thank you for watching")."""
    return chunk_db < file_db - margin


@contextmanager
def chunked(media, seconds=0, chunk=20):
    """Yield (sorted chunk paths, file mean dB). The chunks live in a temp dir that is removed on exit.
    seconds > 0 caps the audio length."""
    need_ffmpeg()
    total = duration(media)
    if seconds:
        total = min(total, float(seconds))
    mean, pauses = _levels(media, seconds)
    cuts = cut_points(pauses, total, chunk)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(media), "-vn", "-ar", "16000", "-ac", "1"]
        if seconds:
            cmd += ["-t", str(seconds)]
        seg = ["-segment_times", ",".join(map(str, cuts))] if cuts else ["-segment_time", str(chunk)]
        done = _run(cmd + ["-f", "segment", *seg, "-c:a", "pcm_s16le", str(Path(tmp) / "c%05d.wav")])
        if done.returncode:
            raise Fail(f"ffmpeg could not cut {media}: {done.stderr.strip()[-300:]}")
        # a cut next to trailing silence can leave a few-millisecond tail that the feature extractors choke on:
        # skip < 0.3 s (9.6 kB of 16-bit 16 kHz audio)
        yield sorted(str(p) for p in Path(tmp).glob("c*.wav") if p.stat().st_size > 9600), mean
