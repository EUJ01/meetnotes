"""Which device and dtype to run the speech models on, and the Windows ROCm exit fix."""
import os
import sys

from meetnotes import Fail


def pick(torch, want="auto"):
    """cuda covers NVIDIA and AMD ROCm builds of PyTorch; then Apple mps; then cpu."""
    has_mps = getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available()
    if want == "auto":
        return "cuda" if torch.cuda.is_available() else "mps" if has_mps else "cpu"
    if want == "cuda" and not torch.cuda.is_available():
        raise Fail(f"--device cuda, but this PyTorch build sees no GPU ({build(torch)}). Run `meetnotes doctor`.", 2)
    if want == "mps" and not has_mps:
        raise Fail("--device mps, but MPS is not available on this machine", 2)
    if want not in ("cuda", "mps", "cpu"):
        raise Fail(f"unknown device '{want}' (auto, cuda, mps or cpu)", 2)
    return want


def dtype(torch, device, bf16=False):
    """Half precision only on a GPU: float16 fails or crawls on the CPU, and MPS lacks some bfloat16 ops."""
    if device == "cuda":
        return torch.bfloat16 if bf16 else torch.float16
    return torch.float32


def build(torch):
    if getattr(torch.version, "hip", None):
        return f"ROCm {torch.version.hip}"
    if torch.version.cuda:
        return f"CUDA {torch.version.cuda}"
    return "CPU-only"


def hard_exit(code):
    """The HIP runtime hangs at normal process shutdown on Windows (os._exit did not help). When a ROCm PyTorch was
    loaded, end the process ourselves with the real exit code, after flushing output. Called once, at the very end
    of the CLI, so it can never cut a later step short."""
    torch = sys.modules.get("torch")
    if os.name != "nt" or torch is None or not getattr(getattr(torch, "version", None), "hip", None):
        return
    sys.stdout.flush()
    sys.stderr.flush()
    import ctypes
    ctypes.windll.kernel32.TerminateProcess(ctypes.c_void_p(-1), code)  # -1 = pseudo-handle for the current process
