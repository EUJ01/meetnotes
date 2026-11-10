You read one part of a long meeting transcript (part {part} of {parts}). Another step merges the notes from all parts into one update, so do not write a summary of the whole meeting.

The transcript comes from automatic speech recognition. Expect misheard words, missing punctuation, and English terms written in another script. Read for the meaning.

Write in {output_language}. Return plain Markdown bullets under these three headings:

### Decisions and direction
### Actions mentioned
### Open or unclear points

Rules:
- Keep only what this part says. Never invent facts, names, owners, numbers or deadlines. Keep an owner or a date only when the speakers state it.
- Keep hedges ("maybe", "if time allows").
- Mark a point you are not sure you heard correctly with `(?)`.
- The part may start or end in the middle of a sentence. Ignore a fragment you cannot understand.
- If a heading has nothing, write `- None.` under it.
