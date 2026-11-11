# meetnotes

Turn a meeting recording into a to-do list. Speech-to-text runs on your machine; any LLM (local, cloud, or a coding agent) writes the summary, grouped to-dos and open questions. [Example output](examples/update.md).

## Install

Needs Python 3.11+, ffmpeg, and [PyTorch for your GPU](https://pytorch.org/get-started/locally/) (install it first).

```
git clone https://github.com/EUJ01/meetnotes && cd meetnotes
pip install .[asr]
meetnotes doctor
```

## Use

```
cp config.example.toml config.toml      # set your LLM
meetnotes run meeting.mp4 --project weekly --date 2026-10-20
```

Best local LLM in our test: Ternary Bonsai 2 27B in LM Studio, reasoning off (about 6 minutes per meeting).

Everything else (platforms, models, Telegram and Drive publishing, troubleshooting): [docs/guide.md](docs/guide.md). Coding agents: [AGENTS.md](AGENTS.md). License: MIT.
