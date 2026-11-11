# meetnotes

Turn a meeting recording into a to-do list your team can act on.

```
recording ──▶ transcript ──▶ update file ──▶ Telegram / Google Drive
  (local speech-to-text)   (any LLM or a        (optional)
                            coding agent)
```

- **Speech-to-text runs on your machine:** NVIDIA, AMD, Apple Silicon or CPU. Any Whisper language, plus a Bangla model.
- **Any LLM writes the update:** local (LM Studio, Ollama), a cloud API, or a coding agent with no API.
- **The output:** a summary, grouped `- [ ]` to-dos, and open questions. See [examples/update.md](examples/update.md).

## Install

You need Python 3.11+ and ffmpeg.

1. Install ffmpeg: `winget install Gyan.FFmpeg` (Windows), `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Linux).
2. Clone and make a virtual environment:
   ```
   git clone https://github.com/EUJ01/meetnotes && cd meetnotes
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   source .venv/bin/activate       # macOS, Linux
   ```
3. Install PyTorch for your GPU **first**. Plain `pip install torch` is CPU-only on Windows.
   - NVIDIA, or AMD on Linux: the command from <https://pytorch.org/get-started/locally/>.
   - AMD on Windows: AMD's ROCm PyTorch wheels.
   - Apple Silicon, or no GPU: `pip install torch`.
4. `pip install .[asr]`
5. `meetnotes doctor` checks the setup and prints a fix for each problem.

Already have transcripts? `pip install .` is enough (no dependencies).

## Quick start

```
cp config.example.toml config.toml          # set your LLM, and where to publish
meetnotes run meeting.mp4 --project weekly --date 2026-10-20
```

Result: `projects/weekly/79738979_2026-10-20_update.md`. The first run downloads the speech model (about 1.6 GB).

Step by step instead:

```
meetnotes transcribe meeting.mp4
meetnotes summarize transcripts/meeting.md --project weekly --date 2026-10-20
meetnotes publish
```

## Which LLM

Tested on a real 26-minute meeting, the best local setup was **Ternary Bonsai 2 27B in LM Studio with reasoning off**: 8.6 GB, about 6 minutes. Full comparison and settings: [docs/guide.md](docs/guide.md#which-local-model).

## More

| Topic | Read |
|---|---|
| LLM providers, model comparison, review agent, project context | [The LLM](docs/guide.md#the-llm) |
| Speech models, languages, Bangla clean-up | [Speech-to-text](docs/guide.md#speech-to-text) |
| File names, Telegram, Google Drive, rclone | [Publishing](docs/guide.md#update-files-and-publishing) |
| Errors, running the tests | [Troubleshooting](docs/guide.md#troubleshooting) |
| Using a coding agent instead of an API | [AGENTS.md](AGENTS.md) |
| Secrets and privacy | [Security](docs/guide.md#security) |

## License

MIT, see [LICENSE](LICENSE). The speech models have their own licenses ([guide](docs/guide.md#speech-to-text)).
