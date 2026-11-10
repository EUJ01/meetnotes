"""Hugging Face Whisper (any language), on the chunks from audio.chunked."""
from collections import Counter

from meetnotes.asr.common import collapse_loops, run_batches


class Whisper:
    def __init__(self, model_id, device, dtype, torch):
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
        self.torch, self.device, self.dtype = torch, device, dtype
        self.processor = WhisperProcessor.from_pretrained(model_id)
        self.model = WhisperForConditionalGeneration.from_pretrained(model_id, dtype=dtype).eval().to(device)

    def _features(self, paths):
        import soundfile as sf
        audio = [sf.read(p, dtype="float32")[0] for p in paths]
        feats = self.processor(audio, sampling_rate=16000, return_tensors="pt").input_features
        return feats.to(self.device, self.dtype)

    def detect(self, paths):
        """Language code by majority vote over a few loud chunks, so code-mixed talk gets one language for the file."""
        with self.torch.no_grad():
            ids = self.model.detect_language(self._features(paths))
        codes = [t.strip("<|>") for t in self.processor.tokenizer.convert_ids_to_tokens(ids.view(-1).tolist())]
        return Counter(codes).most_common(1)[0][0]

    def transcribe(self, paths, language, batch, log):
        def run(part):
            with self.torch.no_grad():
                # greedy: beam search is not needed here and keeps memory flat. Bangla costs several byte-level
                # tokens per character; 448 is the decoder limit, minus the forced start tokens
                gen = self.model.generate(self._features(part), language=language, task="transcribe",
                                          num_beams=1, do_sample=False, max_new_tokens=440)
            return [collapse_loops(t.strip()) for t in self.processor.batch_decode(gen, skip_special_tokens=True)]
        return run_batches(paths, batch, run, self.torch.cuda.empty_cache, log)
