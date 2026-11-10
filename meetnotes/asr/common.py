"""Shared by the speech models: loop collapse, batches that shrink on out-of-memory, chunk loudness."""
import math
import re

LOOP = re.compile(r"(\S+(?:\s+\S+){0,11}?)(?:\s+\1){3,}")  # a 1-12 word phrase repeated 4+ times in a row


def collapse_loops(text):
    return LOOP.sub(r"\1", text)


def is_oom(err):
    return "out of memory" in str(err).lower()  # CUDA and HIP both say it; OutOfMemoryError is a RuntimeError


def run_batches(items, batch, fn, empty_cache, log):
    """fn(list) -> list of the same length. On a GPU out-of-memory error, halve the batch and retry that part."""
    out, i = [], 0
    while i < len(items):
        part = items[i:i + batch]
        try:
            res = fn(part)
        except RuntimeError as e:
            if not is_oom(e) or batch == 1:
                raise
            batch //= 2
            empty_cache()
            log(f"out of GPU memory: batch size now {batch}")
            continue
        out += res
        i += len(part)
        log(f"{len(out)}/{len(items)} chunks")
    return out


def chunk_db(path):
    """Mean level of a wav chunk in dB, comparable with ffmpeg volumedetect's mean_volume."""
    import numpy as np
    import soundfile as sf
    data, _ = sf.read(path, dtype="float32")
    rms = float(np.sqrt(np.mean(np.square(data)))) if len(data) else 0.0
    return 20 * math.log10(max(rms, 1e-10))
