# demo update: 2026-10-20

Source: `transcript.md` (412 words). Summary by qwen/qwen3.5-9b. Machine transcript: check important points against the recording.
<!-- meetnotes source: transcript.md -->

## Summary
- **Beta Feedback** Addressed search ranking issue where ingredient matches rank higher than titles for queries like "chicken".
  - Proposal to weight title matches three times more than ingredient matches.
- **Offline Mode Sync** Decision deferred offline mode release after next release due to unfixable sync bug currently.
  - Will implement conflict screen when both versions changed instead of merging data.
- **App Store Review** Update rejected because privacy page does not mention analytics usage.
  - Must update privacy page and resubmit before legal review.
- **Server Costs** Usage costs increased last month without a clear reason identified yet.

## To do before the next update
### 1. Search Improvements
- [ ] Weight title matches three times more than ingredient matches in search ranking logic (?)
- [ ] Write twenty search queries with expected results for test set verification
- [ ] Check expected results against search output to confirm improvement

### 2. Offline Mode Design
- [ ] Draft the conflict screen design for showing users when versions changed
- [ ] Review conflict screen design next week if time allows

### 3. App Store Compliance
- [ ] Update privacy page to include analytics disclosure and resubmit app store update
- [ ] Find owner of privacy page or write new draft ourselves before legal check

### 4. Server Costs
- [ ] Review billing details to identify reason for increased costs last month (?)

## Open questions
- Who owns the current privacy page (speaker thinks marketing but is not sure) (?)
- Exact cause of server cost increase (maybe image resizing, needs bill review) (?)
- Which two people will write/search check the twenty queries for search test set
