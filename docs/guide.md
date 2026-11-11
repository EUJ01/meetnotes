# meetnotes guide

- [Install](#install)
- [The LLM](#the-llm)
- [Speech-to-text](#speech-to-text)
- [Update files and publishing](#update-files-and-publishing)
- [Troubleshooting](#troubleshooting)
- [Security](#security)

## Install

1. Install ffmpeg: `winget install Gyan.FFmpeg` (Windows), `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Linux).
2. Clone and make a virtual environment:
   ```
   git clone https://github.com/EUJ01/meetnotes && cd meetnotes
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # macOS, Linux
   ```
3. Install PyTorch for your hardware **first**. Plain `pip install torch` gives a CPU-only build on Windows.
   - NVIDIA, or AMD on Linux: the command from the selector at <https://pytorch.org/get-started/locally/>.
   - AMD on Windows: AMD's ROCm PyTorch wheels. Tested: PyTorch 2.9.1 with ROCm 7.2 on a Radeon RX 9060 XT.
   - Apple Silicon: `pip install torch` (includes MPS).
   - No GPU: `pip install torch` works, but expect about 10 times slower than real time with the default model.
4. `pip install .[asr]`, then `meetnotes doctor`. Each failed check prints a fix.

Only need the LLM and publishing steps (you already have transcripts)? `pip install .` is enough. It has no dependencies.

The steps of `meetnotes run`, one by one:

```
meetnotes transcribe meeting.mp4 --seconds 60      # a quick test: transcripts/meeting.first60s.md
meetnotes transcribe meeting.mp4                   # -> transcripts/meeting.md
meetnotes summarize transcripts/meeting.md --project weekly --date 2026-10-20
meetnotes publish --dry-run
meetnotes publish
```

The first run downloads the speech model (about 1.6 GB for Whisper, 1.5 GB for the Bangla model).

## The LLM

Any OpenAI-compatible endpoint works. Set it in `config.toml`:

```toml
[llm]
base_url = "http://localhost:1234/v1"
model = "qwen3-8b"
api_key_env = ""            # for a cloud API: the NAME of the environment variable that holds the key
```

| Provider | base_url | Key |
|---|---|---|
| LM Studio | `http://localhost:1234/v1` | none |
| Ollama | `http://localhost:11434/v1` | none |
| llama.cpp (`llama-server`) | `http://localhost:8080/v1` | none |
| vLLM | `http://localhost:8000/v1` | none |
| OpenAI | `https://api.openai.com/v1` | `api_key_env = "OPENAI_API_KEY"` |
| OpenRouter | `https://openrouter.ai/api/v1` | `api_key_env = "OPENROUTER_API_KEY"` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `api_key_env = "GEMINI_API_KEY"` |
| Anthropic | `https://api.anthropic.com/v1` | `api_key_env = "ANTHROPIC_API_KEY"` |

- Tested with Qwen 3.5 9B in LM Studio: a 412-word meeting took about 2 minutes. Always check the update against the recording.
- Long transcripts are noted part by part, then merged (`max_input_chars`, default 12,000). This matters for local models with a small context window.
- **Ollama** silently cuts prompts longer than its context window. Raise it, for example with the environment variable `OLLAMA_CONTEXT_LENGTH=16384`, or lower `max_input_chars`.
- Reasoning models are fine: their `<think>` blocks are removed. If the reasoning eats the whole answer, raise `max_tokens` (16000 was enough in our tests), or turn reasoning off with `reasoning_effort = "none"`. `reasoning_effort_light = "none"` turns it off only for translation and the per-part minutes.
- The reply must have the three sections. If one is missing, the tool asks once more. If it still fails, it saves the raw reply as `.failed.md` and writes no update file.
- Replies are streamed, so `timeout` is the longest silence allowed, not the length of the whole answer. A slow local model can write for 10 minutes. A timeout is not retried, because the server may still be working on the first request.
- The prompt is [meetnotes/prompts/update.md](../meetnotes/prompts/update.md). It tells the model never to invent owners or deadlines, to keep hedges, and to mark unsure points with `(?)`.
- The update's header (source, date, length, models) is written by the tool, not the LLM.

**No API?** Use a coding agent: `meetnotes new-update transcripts/meeting.md --project weekly` creates the file with empty sections, and the agent fills them in from the same prompt. Point your agent at [AGENTS.md](../AGENTS.md).

### Which local model

We ran `summarize` on one 26-minute Bangla research meeting (3,388 words, translated to English first) and scored each update against a hand-written list of 9 key points. LM Studio, AMD RX 9060 XT (16 GB VRAM), 32k context.

| Model (GGUF) | Size | Key points (of 9) | Time | Notes |
|---|---|---|---|---|
| Qwen 3.5 9B (LM Studio default) | 6.5 GB | 6.5 to 7 | 7 to 10 min | Sometimes guessed what an acronym stands for |
| Qwen 3.5 35B-A3B, Q4_K_M | 22 GB | 7 | 24 min | Did not fit in VRAM, partly ran on the CPU. Added two to-dos nobody said |
| Ternary Bonsai 2 27B, reasoning on | 8.6 GB | 6.5 to 7 | 21 min | Most method detail, but named owners the meeting did not state |
| **Ternary Bonsai 2 27B, reasoning off** | 8.6 GB | 6.5 to 7 | **6 min** | Recommended: same score, unclear terms went to open questions |

- The Bonsai runs reused a saved translation, so their times leave out the translation step.
- All four missed the same few points. Those points were garbled in the speech-to-text output, so no model could recover them. A better model does not fix a bad transcript.
- One meeting is a small test. Treat the scores as a rough guide.

Settings for the recommended model:

```toml
[llm]
model = "ternary-bonsai-2-27b"
reasoning_effort = "none"   # reasoning on took 3.5 times longer for the same score
max_tokens = 8000
```

### The review agent

Optional (`review = true` in `[llm]`). After the first draft, a review agent checks it against the transcript and the minutes. It has two tools: `search_transcript` (find passages by words) and `read_part` (read one part in full). It adds actions and time frames the draft missed, marks unsupported to-dos with `(?)`, puts the work in the agreed order, and fixes misheard names.

- It needs a model and server with tool calling (LM Studio, Ollama, llama.cpp, vLLM and the cloud APIs support it for most recent models).
- It uses at most 6 tool calls. If anything goes wrong (no tool support, a bad reply), the draft is kept.
- It is off by default. With a 9B local model it scored no higher than the draft and twice added a wrong claim (a reversed priority, an invented confirmation). With Bonsai 27B it once fixed a reversed priority in the draft, and once added a doubtful detail. Turn it on if your model handles tools well, and compare with the `.draft.md`.
- The draft before the review is kept as `.draft.md`, next to the update.
- Why: summarizing in parts loses links between parts, and each merge step can add made-up content. Giving the model the original text back at the end reduces that (Ou and Lapata, ACL 2025).

### Help the model with context (optional)

Speech recognition mishears names and jargon. Tell the model what a project is about and which names come up, once per project:

```toml
[projects.weekly]
context = "Weekly sync of the mobile app team."
terms = ["Kotlin", "Firebase", "Priya", "Q3 roadmap"]
```

The previous update of the same project is also given to the model as context, so a follow-up meeting can refer to last week's tasks. For long meetings, the minutes taken from each part are kept next to the update as `.minutes.md`, so you can see where a point came from.

## Speech-to-text

| Language | Default model | License | Notes |
|---|---|---|---|
| Any (auto-detected) | [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | MIT | Pick another with `--model` or `[transcribe] model` |
| Bangla (`--language bn`, or detected) | [SayedShaun/Qwen3-ASR-0.6B-Bengali](https://huggingface.co/SayedShaun/Qwen3-ASR-0.6B-Bengali) | Apache-2.0 | Whisper is poor at Bangla |

- `--language auto` (the default) detects the language once, from the loudest of the first chunks. Then it keeps that language for the whole file, so code-mixed speech does not flip between languages. Bangla switches to the Bangla model.
- The audio is cut at pauses into chunks of 20 seconds or less. Silent chunks are skipped, because Whisper invents text on silence.
- On a GPU out-of-memory error the batch size halves itself. Set it with `--batch`.
- A transcript that exists is not made again (an hour of GPU time). Use `--force` to redo it, for example with another `--language` or `--model`.
- `--seconds N` transcribes only the first N seconds, into its own file. `run --seconds` stops before publishing.

Measured on an AMD Radeon RX 9060 XT (16 GB): 63.5 minutes of Bangla audio in 11.2 minutes with the Bangla model. On a mixed Bangla-English test clip, the Bangla model reached 22.4% word error rate, and Whisper large-v3 98.1% (most speech lost).

Other options, not built in: [whisper.cpp](https://github.com/ggml-org/whisper.cpp) with its Vulkan backend is faster on AMD GPUs. NeMo FastConformer models are faster for Bangla, but less accurate.

### Bangla clean-up (optional)

Bangla models write English terms in Bangla script. A glossary turns them back into English (the Bangla ending stays: words-গুলো). Copy `glossary.example.json`, add your terms, set `[clean] glossary`, then `meetnotes clean transcripts/meeting.md --report`. The report lists every replacement, so you can check the guesses.

## Update files and publishing

### Update files

`projects/<project>/<key>_<date>_update.md`. The key is 99999999 minus the date as YYYYMMDD, so the newest update sorts first in any file list.

- The date comes from `--date`, else from the recording's file date. A downloaded recording has the download date, so pass `--date`.
- A second meeting on the same day gets `<key>_<date>_2_update.md`. Running the same recording again replaces its own file.
- The header names the recording's file name (never its folder). Rename a file such as `salary review.mp4` before you publish its update.

### Publishing

`meetnotes publish` sends every new or changed update file to each configured target. `.meetnotes/ledger.tsv` remembers what each target has, so a target that failed catches up on the next run. Deleting a local file does not delete the remote copy.

**Telegram**

1. Create a bot with @BotFather. Put its token in an environment variable: `TELEGRAM_BOT_TOKEN`.
2. Add the bot to your channel as an admin with the right to post (or to a group as a member).
3. Post any message in the channel, then run `meetnotes publish --list-chats` to see its id.
4. Map projects to chats:
   ```toml
   [publish.telegram.chats]
   weekly = "-100..."
   ```

**Google Drive, OneDrive, Dropbox, Syncthing**: with the desktop app, point at the synced folder. The folder must exist (an unmounted drive gives an error, not a new folder):

```toml
[publish.folder]
path = "G:/My Drive/meeting-notes"
```

**Any rclone remote** (a server without a Drive app): run `rclone config` once, then:

```toml
[publish.rclone]
remote = "gdrive:meeting-notes"
```

## Troubleshooting

- Start with `meetnotes doctor`. Each failed check prints a fix.
- `PyTorch ... CPU-only` on a machine with a GPU: reinstall PyTorch for your GPU ([Install](#install), step 3).
- The transcript is in the wrong language: run it again with `--language <code> --force`.
- `... belongs to another recording or length`: a transcript with that name exists. Use `--out` or `--force`.
- LM Studio on Windows says `listen EACCES: permission denied 127.0.0.1:1234`: Windows reserved that port (Hyper-V, WSL and Docker reserve port ranges). Check with `netsh interface ipv4 show excludedportrange protocol=tcp`, pick a port outside the ranges (for example 8765) in LM Studio's server settings, and use it in `base_url`.
- Windows with an AMD GPU: the ROCm runtime can hang when Python exits. meetnotes ends its own process after the work is done to avoid this.

### Development

```
python -m unittest discover -s tests -t .
```

The tests need no GPU, network or ffmpeg. `tests/test_secrets.py` fails if a file holds something that looks like a token. Keep secrets in environment variables.

## Security

- Secrets (API keys, the bot token) come only from environment variables. `config.toml` names the variable, never the value.
- An API key is sent only over https, or to a server on your own machine. Redirects are never followed, so a key cannot be passed on to another host.
- Speech models load as safetensors weights, with no remote code. Use model ids you trust.
- Recordings stay on your machine. The transcript text goes to the LLM endpoint you configure, and the update file goes to your publish targets. With a local LLM, nothing leaves your machine except what you publish.
- A transcript is untrusted text. Someone in a meeting could say "ignore your instructions". The worst result is a wrong update file, so read it before you publish.

To report a security problem, open a GitHub issue without the details and ask for a private contact.
