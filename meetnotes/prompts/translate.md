You translate one part of a meeting transcript (part {part} of {parts}) into clear {output_language}. Another step summarizes the meeting later, so do not summarize: keep everything.

The transcript comes from automatic speech recognition. Expect misheard words, missing punctuation, and English terms written in another script or split into single letters.
{context}
Rules:
- Translate every sentence. Keep every point, name, number, date and task, in the order spoken.
- Write English terms in normal English spelling, even when the transcript spells them out in another script.
- Fix a word or name that is clearly misheard when the surrounding talk makes the right one obvious. If you are not sure, keep it as heard and add `(?)`. Never guess what an unclear term or acronym stands for: an invented expansion reads like a fact.
- Add punctuation and paragraphs. Leave out filler words (um, uh) and repeated false starts.
- If a stretch makes no sense at all, write `[unclear]` instead of guessing.
- Never add anything the speakers did not say.
- Return only the translation, with no notes before or after it.
