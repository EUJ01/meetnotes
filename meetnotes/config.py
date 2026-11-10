"""Settings: config.toml (see config.example.toml) on top of the defaults below. Secrets come only from
environment variables, named in the config, so the config file is safe to show."""
import copy
import tomllib
from pathlib import Path

from meetnotes import Fail

DEFAULTS = {
    "workspace": ".",  # transcripts/, projects/ and .meetnotes/ go here; relative to the config file
    "transcribe": {
        "language": "auto",  # auto, or a code such as en, de, bn
        "model": "openai/whisper-large-v3-turbo",  # any Hugging Face Whisper model
        "model_bn": "SayedShaun/Qwen3-ASR-0.6B-Bengali",  # used for Bangla (Whisper is poor at it)
        "device": "auto",  # auto, cuda (NVIDIA and AMD ROCm), mps, cpu
        "batch": 8,
    },
    "clean": {"glossary": ""},  # Bangla glossary file; empty = skip the clean step
    "llm": {
        "base_url": "",  # an OpenAI-compatible endpoint, for example http://localhost:1234/v1 (LM Studio)
        "model": "",
        "api_key_env": "",  # NAME of the environment variable that holds the key; empty for local servers
        "max_tokens": 4000,
        "temperature": None,  # sent only when set: some reasoning models reject it
        "timeout": 300,
        "max_input_chars": 12000,  # longer transcripts are summarized in parts first
        "output_language": "English",
        "reasoning_effort": "",  # sent with every request when set (OpenAI-style: none, low, medium, high)
        "reasoning_effort_light": "",  # sent for translation and minutes; "none" makes reasoning models fast there
        "translate": "auto",  # auto: translate a transcript that is not in English first (when output is English)
        "review": False,  # a review agent checks the draft against the transcript with tools (needs tool calling).
        # Off by default: with a 9B local model it added errors and no points (README, "The review agent")
    },
    # per project: context = what the project is about, terms = names the speech model mishears. Both help the LLM
    # read the transcript. [projects.weekly] context = "..." terms = ["GRPO", "LangChain"]
    "projects": {},
    "publish": {
        "telegram": {"token_env": "TELEGRAM_BOT_TOKEN", "chats": {}},  # chats: project = "chat id"
        "folder": {"path": ""},  # for example G:/My Drive/meeting-notes (Google Drive for desktop)
        "rclone": {"remote": ""},  # for example gdrive:meeting-notes
    },
}


def _merge(base, over, where=""):
    for key, value in over.items():
        if key not in base:
            raise Fail(f"config: unknown setting '{where}{key}'", 2)
        if key == "projects":
            for name, proj in (value.items() if isinstance(value, dict) else [(None, None)]):
                if not isinstance(proj, dict) or set(proj) - {"context", "terms"}:
                    raise Fail("config: each [projects.<name>] table takes only context = \"...\" and terms = [...]", 2)
        if key == "chats" and not isinstance(value, dict):
            raise Fail("config: [publish.telegram.chats] must be a table of project = \"chat id\"", 2)
        if key == "translate" and value not in (True, False, "auto"):
            raise Fail("config: [llm] translate must be true, false or \"auto\"", 2)
        if key == "batch" and (not isinstance(value, int) or value < 1):
            raise Fail("config: [transcribe] batch must be a whole number, 1 or more", 2)
        if isinstance(base[key], dict) and key not in ("chats", "projects"):
            if not isinstance(value, dict):
                raise Fail(f"config: '{where}{key}' must be a table", 2)
            _merge(base[key], value, f"{where}{key}.")
        else:
            base[key] = value


def load(path=None):
    """Return (settings dict, workspace Path). No file is fine: the defaults run transcription only."""
    cfg = copy.deepcopy(DEFAULTS)
    file = Path(path) if path else Path("config.toml")
    if path and not file.exists():
        raise Fail(f"config file not found: {file}", 2)
    if file.exists():
        try:
            _merge(cfg, tomllib.loads(file.read_text(encoding="utf-8")))
        except tomllib.TOMLDecodeError as e:
            raise Fail(f"config: {file}: {e}", 2)
    base = file.resolve().parent if file.exists() else Path.cwd()
    for section, key in (("clean", "glossary"), ("folder", "path")):  # relative paths: relative to the config file
        holder = cfg["publish"] if section == "folder" else cfg
        if holder[section][key]:
            holder[section][key] = str((base / Path(holder[section][key]).expanduser()).resolve())
    cfg["_file"] = str(file.resolve()) if file.exists() else ""
    return cfg, (base / cfg["workspace"]).resolve()
