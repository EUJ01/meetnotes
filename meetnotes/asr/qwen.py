"""Qwen3-ASR fine-tunes, used for Bangla (SayedShaun/Qwen3-ASR-0.6B-Bengali)."""
import re

from meetnotes import Fail
from meetnotes.asr.common import LOOP, collapse_loops, run_batches

CHUNK = 20  # seconds, matches audio.chunked (the model was trained on clips up to 20 s)
TOKENS_PER_SEC = 30  # model card: a safe rate; a smaller max_new_tokens silently truncates
LANGUAGES = {"bn": "Bengali", "en": "English"}


class Qwen:
    def __init__(self, model_id, device, dtype, torch):
        from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration
        self.torch = torch
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = Qwen3ASRForConditionalGeneration.from_pretrained(model_id, dtype=dtype).eval().to(device)

    def _run(self, paths, language, **kw):
        prefix = f"language {LANGUAGES[language]}<asr_text>"
        conversations = [[
            {"role": "user", "content": [{"type": "audio", "path": path}]},
            {"role": "assistant", "content": [{"type": "text", "text": prefix}]},
        ] for path in paths]
        inputs = self.processor.apply_chat_template(
            conversations, tokenize=True, return_dict=True, padding=True, continue_final_message=True
        ).to(self.model.device, self.model.dtype)
        with self.torch.no_grad():
            gen = self.model.generate(**inputs, max_new_tokens=CHUNK * TOKENS_PER_SEC, do_sample=False, **kw)
        texts = []
        for text in self.processor.batch_decode(gen[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True):
            text = text.split("<asr_text>", 1)[-1]
            # the model drifts into glossing words with an English/Bangla echo in braces ("মনিটর {monitor}"); drop them
            text = re.sub(r"\s*\{[^}]*\}", "", text)
            texts.append(re.sub(r"(^|\s)-{2,}(?=\s|$)", "", text).strip())  # "--" marks a sentence cut at the chunk edge
        return texts

    def transcribe(self, paths, language, batch, log):
        if language not in LANGUAGES:
            raise Fail(f"the Qwen3-ASR backend here handles {', '.join(LANGUAGES)}, not '{language}'", 2)
        texts = run_batches(paths, batch, lambda part: self._run(part, language), self.torch.cuda.empty_cache, log)
        # a chunk where the model got stuck repeating a word or phrase: decode it again with a repetition penalty,
        # then collapse whatever loop is left (the penalty is off by default because it can hurt normal chunks)
        for i, text in enumerate(texts):
            if LOOP.search(text):
                texts[i] = self._run([paths[i]], language, repetition_penalty=1.3)[0]
                log(f"chunk {i} looped, retried")
        return [collapse_loops(t) for t in texts]
