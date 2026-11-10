# meetnotes

Turn a meeting recording into a to-do list your team can act on.

```
recording ──▶ transcript ──▶ update file ──▶ Telegram / Google Drive
  (local speech-to-text)   (any LLM or a        (optional)
                            coding agent)
```

- **Speech-to-text runs on your machine.** NVIDIA, AMD (ROCm), Apple Silicon, or the CPU. Any language Whisper knows, plus a dedicated Bangla model.
- **Any LLM writes the update.** A local one (LM Studio, Ollama, llama.cpp), a cloud API (OpenAI, OpenRouter, Gemini, Anthropic), or no API at all: a coding agent fills in the file (see [AGENTS.md](AGENTS.md)).
- **The update file** has a summary, grouped `- [ ]` to-dos, and open questions. See [examples/update.md](examples/update.md), made from the fictional meeting in [examples/transcript.md](examples/transcript.md) by a small local model (Qwen 3.5 9B in LM Studio), unedited.
- **Optional publishing** to a Telegram channel per project, to a Google Drive folder, or to any rclone remote. Changed files are re-sent; Telegram replaces the old post in place.

## Install

Python 3.11 or newer, and ffmpeg.

1. Install ffmpeg: Windows `winget install Gyan.FFmpeg`, macOS `brew install ffmpeg`, Linux `sudo apt install ffmpeg`.
2. Get the code and make a virtual environment:
   ```
   git clone <this repository> meetnotes && cd meetnotes
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # macOS, Linux
   ```
3. Install PyTorch for your hardware **first**. Plain `pip install torch` gives a CPU-only build on Windows.
   - NVIDIA (Windows, Linux): the CUDA command from the selector at <https://pytorch.org/get-started/locally/>.
   - AMD on Linux: the ROCm command from the same selector.
   - AMD on Windows: AMD's ROCm PyTorch wheels (see AMD's ROCm documentation). Tested: PyTorch 2.9.1 with ROCm 7.2 on a Radeon RX 9060 XT.
   - Apple Silicon: `pip install torch` (includes MPS).
   - No GPU: `pip install torch` works, but expect about 10 times slower than real time with the default model.
4. Install meetnotes with the speech-to-text extra: `pip install .[asr]`.
5. Check: `meetnotes doctor`.

Only need the LLM and publishing steps (for example, you already have transcripts)? `pip install .` is enough. It has no dependencies.

## Quick start

```
cp config.example.toml config.toml          # then edit it: the LLM, and where to publish
meetnotes run meeting.mp4 --project weekly --date 2026-10-20
```

That transcribes `meeting.mp4`, writes `projects/weekly/79738979_2026-10-20_update.md`, and publishes it if a target is set. Steps one by one:

```
meetnotes transcribe meeting.mp4 --seconds 60      # a quick test: transcripts/meeting.first60s.md
meetnotes transcribe meeting.mp4                   # -> transcripts/meeting.md
meetnotes summarize transcripts/meeting.md --project weekly --date 2026-10-20
meetnotes publish --dry-run
meetnotes publish
```

The first run downloads the speech model (about 1.6 GB for Whisper, 1.5 GB for the Bangla model).

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

- Tested with Qwen 3.5 9B in LM Studio: a 412-word meeting took about 2 minutes. On a 26-minute Bangla meeting it got the main decisions, but garbled some technical terms. Larger models do better: always check the update against the recording.
- Long transcripts are noted part by part, then merged (`max_input_chars`, default 12,000). This matters for local models with a small context window.
- **Ollama** silently cuts prompts longer than its context window. Raise it, for example with the environment variable `OLLAMA_CONTEXT_LENGTH=16384`, or lower `max_input_chars`.
- Reasoning models are fine: their `<think>` blocks are removed. If the reasoning eats the whole answer, raise `max_tokens`.
- The reply must have the three sections. If one is missing, the tool asks once more. If it still fails, it saves the raw reply as `.failed.md` and writes no update file.
- Replies are streamed, so `timeout` is the longest silence allowed, not the length of the whole answer. A slow local model can write for 10 minutes. A timeout is not retried, because the server may still be working on the first request.
- The prompt is [meetnotes/prompts/update.md](meetnotes/prompts/update.md). It tells the model never to invent owners or deadlines, to keep hedges, and to mark unsure points with `(?)`.
- The update's header (source, date, length, models) is written by the tool, not the LLM.

**No API?** Use a coding agent: `meetnotes new-update transcripts/meeting.md --project weekly` creates the file with empty sections, and the agent fills them in from the same prompt. Point your agent at [AGENTS.md](AGENTS.md).

### The review agent

After the first draft, a review agent checks it against the transcript. It has two tools: `search_transcript` (find passages by words) and `read_part` (read one part in full). It removes to-dos the transcript does not support, adds actions and time frames the draft missed, puts the work in the agreed order, and fixes misheard names.

- It needs a model and server with tool calling (LM Studio, Ollama, llama.cpp, vLLM and the cloud APIs support it for most recent models).
- It uses at most 6 tool calls. If anything goes wrong (no tool support, a bad reply), the draft is kept: the review never makes the result worse.
- The draft before the review is kept as `.draft.md`, next to the update. Turn the agent off with `review = false` in `[llm]`.
- Why: summarizing in parts loses links between parts, and each merge step can add made-up content. Giving the model the original text back at the end reduces that (Ou and Lapata, ACL 2025).

### Help the model with context (optional)

Speech recognition mishears names and jargon. Tell the model what a project is about and which names come up, once per project:

```toml
[projects.weekly]
context = "Weekly sync of the mobile app team."
terms = ["Kotlin", "Firebase", "Priya", "Q3 roadmap"]
```

The previous update of the same project is also given to the model as context, so a follow-up meeting can refer to last week's tasks. For long meetings, the minutes taken from each part are kept next to the update as `.minutes.md`, so you can see where a point came from.

## Update files

`projects/<project>/<key>_<date>_update.md`. The key is 99999999 minus the date as YYYYMMDD, so the newest update sorts first in any file list.

- The date comes from `--date`, else from the recording's file date. A downloaded recording has the download date, so pass `--date`.
- A second meeting on the same day gets `<key>_<date>_2_update.md`. Running the same recording again replaces its own file.
- The header names the recording's file name (never its folder). Rename a file such as `salary review.mp4` before you publish its update.

## Publishing

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
- `PyTorch ... CPU-only` on a machine with a GPU: reinstall PyTorch for your GPU (Install, step 3).
- The transcript is in the wrong language: run it again with `--language <code> --force`.
- `... belongs to another recording or length`: a transcript with that name exists. Use `--out` or `--force`.
- LM Studio on Windows says `listen EACCES: permission denied 127.0.0.1:1234`: Windows reserved that port (Hyper-V, WSL and Docker reserve port ranges). Check with `netsh interface ipv4 show excludedportrange protocol=tcp`, pick a port outside the ranges (for example 8765) in LM Studio's server settings, and use it in `base_url`.
- Windows with an AMD GPU: the ROCm runtime can hang when Python exits. meetnotes ends its own process after the work is done to avoid this.

## Security

- Secrets (API keys, the bot token) come only from environment variables. `config.toml` names the variable, never the value.
- An API key is sent only over https, or to a server on your own machine. Redirects are never followed, so a key cannot be passed on to another host.
- Speech models load as safetensors weights, with no remote code. Use model ids you trust.
- Recordings stay on your machine. The transcript text goes to the LLM endpoint you configure, and the update file goes to your publish targets. With a local LLM, nothing leaves your machine except what you publish.
- A transcript is untrusted text. Someone in a meeting could say "ignore your instructions". The worst result is a wrong update file, so read it before you publish.

## Development

```
python -m unittest discover -s tests -t .
```

The tests need no GPU, network or ffmpeg. `tests/test_secrets.py` fails if a file holds something that looks like a token. Keep secrets in environment variables.

## License

MIT, see [LICENSE](LICENSE). The speech models have their own licenses (table above).
