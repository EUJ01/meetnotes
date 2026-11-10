# Instructions for coding agents

This file is for any coding agent (Codex, Gemini CLI, Cursor, Claude Code, Aider, and others) working in this repository or using it to process a meeting. Humans: see README.md.

## What the tool does

`meetnotes` turns a meeting recording into an update file: a summary, grouped to-dos, and open questions.

```
recording -> transcribe -> transcripts/<name>.md -> (clean, Bangla only) -> summarize -> projects/<project>/<file>_update.md -> publish
```

All paths are relative to the workspace (`workspace` in `config.toml`, default: the folder of `config.toml`, or the current folder).

## Process a recording

1. Check the setup: `meetnotes doctor`. Fix any `[!!]` line before you continue.
2. Transcribe: `meetnotes transcribe <recording> [--language bn] [--seconds 60]`. It prints the transcript path. An hour of audio takes several minutes on a GPU. Use `--seconds 60` for a quick test.
3. If the transcript is Bangla and `[clean] glossary` is set: `meetnotes clean <transcript>`. It prints the `.clean.md` path. Use that file from now on.
4. Make the update file, with route A or route B.
5. Publish: `meetnotes publish --dry-run`, check the list, then `meetnotes publish`.

`meetnotes run <recording> --project <name>` does steps 2 to 5 in one go when an LLM is configured.

### Route A: the configured LLM

`meetnotes summarize <transcript> --project <name> [--date YYYY-MM-DD]`. It prints the update file path.

- If it fails, read the error. Unreachable server: start the server or fix `[llm] base_url`. A reply with missing sections: the raw reply is saved next to the update path as `.failed.md`.
- Next to the update file it keeps `.minutes.md` (the minutes of each part, for long meetings) and `.draft.md` (the update before the review agent ran). Use them to see where a point came from.

### Route B: you write the update (no API needed)

1. Run `meetnotes new-update <transcript> --project <name> [--date YYYY-MM-DD]`. It creates the file with a header and three empty sections, and prints its path. If the file exists already, it prints the path and changes nothing.
2. Read the transcript. Skip the front matter block between the `---` lines.
3. Read `meetnotes/prompts/update.md`. Follow it exactly. It is the same prompt the API route uses.
4. Fill in the three sections of the update file. Keep the header lines that the tool wrote. Do not change the headings.
5. Run `meetnotes publish`.

Rules that matter most (the prompt has all of them):

- Never invent names, owners, numbers or deadlines. The transcript is machine-made: mark a point you are not sure you heard right with `(?)`.
- Keep hedges ("maybe", "if time allows").
- Write in the `output_language` of the config (default English), even for a Bangla transcript.

## The meeting date

The date comes from `--date`, else from the recording's file date (`recorded` in the transcript front matter). A downloaded file has the download date. If the user told you the meeting date, pass `--date`.

## Work on the code

- Python 3.11+. The core uses only the standard library. Speech-to-text needs PyTorch and `pip install .[asr]`.
- Run the tests before and after a change: `python -m unittest discover -s tests -t .` (no GPU, network or ffmpeg needed).
- Keep secrets out of files: tokens and keys come from environment variables named in the config. `tests/test_secrets.py` fails on a token-like string.
- Layout: `meetnotes/cli.py` (commands), `asr/` (speech models), `audio.py` (ffmpeg chunking), `summarize.py` + `llm.py` (LLM step, streamed, with tool calls), `agent.py` (the review agent and its two tools), `prompts/` (update, notes, review), `update.py` (file names, header), `publish/` (Telegram, folder, rclone).
