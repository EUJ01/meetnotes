# Speech-to-text

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

## Bangla clean-up (optional)

Bangla models write English terms in Bangla script. A glossary turns them back into English (the Bangla ending stays: words-গুলো). Copy `glossary.example.json`, add your terms, set `[clean] glossary`, then `meetnotes clean transcripts/meeting.md --report`. The report lists every replacement, so you can check the guesses.
