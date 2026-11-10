"""transcribe(): recording -> text. torch and transformers are imported only here, so the other steps run without them."""
import gc
import os
import sys

from meetnotes import Fail, audio, device as dev


def _torch():
    if sys.platform == "darwin":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")  # ops MPS lacks fall back to the CPU
    try:
        import torch
        import transformers
        import numpy  # noqa: F401
        import soundfile  # noqa: F401
        transformers.logging.set_verbosity_error()  # hide deprecation chatter; real errors still raise
    except ImportError as e:
        raise Fail(f"speech-to-text needs PyTorch and the [asr] extra ({e.name} is missing). "
                   "Install PyTorch for your GPU first (see README), then: pip install .[asr]")
    return torch


def is_qwen(model_id):
    return "qwen3-asr" in model_id.lower()


def _load(model_id, where, torch):
    if is_qwen(model_id):
        from meetnotes.asr.qwen import Qwen
        return Qwen(model_id, where, dev.dtype(torch, where, bf16=True), torch)
    from meetnotes.asr.whisper import Whisper
    return Whisper(model_id, where, dev.dtype(torch, where), torch)


def _join(texts):
    return " ".join(t for t in texts if t)  # skip empty chunks so there are no double spaces


def transcribe(media, *, language, override, whisper_model, bn_model, device, batch, seconds, log):
    """Return (language, model id, text).
    override = a model the user named (--model), else whisper_model, or bn_model for Bangla.
    language 'auto' is detected once, by Whisper, from the 3 loudest of the first 10 chunks; Bangla then switches
    to bn_model, because Whisper is poor at Bangla."""
    torch = _torch()
    where = dev.pick(torch, device)
    log(f"device: {where} ({dev.build(torch)})")
    if where == "cpu":
        # measured: whisper-large-v3-turbo took 5.5 min for 30 s of audio on a desktop CPU, model load included
        log("warning: running on the CPU, which is about 10 times slower than real time with the default model. "
            "A smaller model helps: --model openai/whisper-base")
    from meetnotes.asr.common import chunk_db
    with audio.chunked(media, seconds) as (chunks, file_db):
        kept = [(p, db) for p, db in ((p, chunk_db(p)) for p in chunks) if not audio.is_quiet(db, file_db)]
        log(f"{len(chunks)} chunks, {len(chunks) - len(kept)} silent ones skipped")
        paths = [p for p, _ in kept]
        if not paths:
            return ("unknown" if language == "auto" else language), override or whisper_model, ""
        if language == "auto":
            if override and is_qwen(override):
                language = "bn"  # the Qwen backend is only used for Bangla here
            else:
                whisper = _load(override or whisper_model, where, torch)
                loudest = sorted(kept[:10], key=lambda pd: -pd[1])[:3]
                language = whisper.detect([p for p, _ in loudest])
                log(f"language detected: {language}")
                if language != "bn" or override:
                    return language, override or whisper_model, _join(whisper.transcribe(paths, language, batch, log))
                del whisper
                gc.collect()
                if where == "cuda":
                    torch.cuda.empty_cache()
        model = override or (bn_model if language == "bn" else whisper_model)
        log(f"model: {model}")
        engine = _load(model, where, torch)
        return language, model, _join(engine.transcribe(paths, language, batch, log))
