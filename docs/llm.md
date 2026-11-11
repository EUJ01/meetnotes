# The LLM

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

## Which local model

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

## The review agent

Optional (`review = true` in `[llm]`). After the first draft, a review agent checks it against the transcript and the minutes. It has two tools: `search_transcript` (find passages by words) and `read_part` (read one part in full). It adds actions and time frames the draft missed, marks unsupported to-dos with `(?)`, puts the work in the agreed order, and fixes misheard names.

- It needs a model and server with tool calling (LM Studio, Ollama, llama.cpp, vLLM and the cloud APIs support it for most recent models).
- It uses at most 6 tool calls. If anything goes wrong (no tool support, a bad reply), the draft is kept.
- It is off by default. With a 9B local model it scored no higher than the draft and twice added a wrong claim (a reversed priority, an invented confirmation). With Bonsai 27B it once fixed a reversed priority in the draft, and once added a doubtful detail. Turn it on if your model handles tools well, and compare with the `.draft.md`.
- The draft before the review is kept as `.draft.md`, next to the update.
- Why: summarizing in parts loses links between parts, and each merge step can add made-up content. Giving the model the original text back at the end reduces that (Ou and Lapata, ACL 2025).

## Help the model with context (optional)

Speech recognition mishears names and jargon. Tell the model what a project is about and which names come up, once per project:

```toml
[projects.weekly]
context = "Weekly sync of the mobile app team."
terms = ["Kotlin", "Firebase", "Priya", "Q3 roadmap"]
```

The previous update of the same project is also given to the model as context, so a follow-up meeting can refer to last week's tasks. For long meetings, the minutes taken from each part are kept next to the update as `.minutes.md`, so you can see where a point came from.
