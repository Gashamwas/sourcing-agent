# Cloris Copy Bank

Living reference for Cloris product language, hero copy, microcopy, and
phrase candidates. This is not a final brand book. It is the working pile of
lines worth trying, lines to avoid, and where each line might belong.

## Operating Rules

- Cloris copy should sound particular, restrained, and dry.
- The line should usually be about Cloris, the work, or the artifact, not about
  the user.
- Avoid eager assistant language.
- Avoid SaaS success language.
- Avoid "AI-native", "powered by", "copilot", "magical", "unlock", "supercharge",
  and anything that sounds like product-marketing filler.
- Character copy should surface sparingly. Most UI copy should be plain.
- Never use character voice in high-stakes states: auth failure, browser
  takeover, runtime failure, stop/kill, data loss, or ambiguous execution state.

## Lines To Kill

These should not ship.

- "She is sorting the pile."
  - Problem: sounds unpleasant and weirdly bodily.
  - Also too passive and too cute for the main hero.

## Hero Line Candidates

Potential replacements for the main Cloris hero line.

- "She left the good ones on top."
  - Current favorite.
  - Best for a populated state where Cloris has results or resumable work.
- "She'll tell you when there's something."
  - Best for idle or empty state.
- "She has the list."
  - Short, confident, slightly ominous.
- "She's making her rounds."
  - Good for active background work.
- "She found a few worth seeing."
  - Good for review-ready state.
- "She's been through the stack."
  - Similar to the old pile line, but less cursed.
- "She knows where everything is."
  - Good for status/home; more character-forward.
- "She's going through it."
  - Funny, but may read as personal distress. Use carefully.

## Character Epithets

Working phrases for Cloris-as-character.

- "The bespectacled busybody."
  - Best character-first option. Funny, nosy, active.
- "The bespectacled bloodhound."
  - Strong sourcing metaphor; more agentic, less grandmotherly.
- "The bespectacled bookkeeper."
  - Ledger/order energy; calmer and less active.
- "The bespectacled backchanneler."
  - Recruiting-specific, but risks startup slang.
- "The bespectacled battleaxe."
  - Funny but harsh. Probably not product UI.
- "The bespectacled biddy."
  - Grandma-coded but pejorative. Avoid unless deliberately sharp.
- "The bespectacled braintrust."
  - Too corporate. Avoid.

## Sewing / Thread / Pattern Language

Useful because it gives Cloris a physical craft grammar without falling back to
dashboard language.

- "Needlework, not guesswork."
  - Strong product line. Good for launch/running state.
- "Give her the pattern."
  - Strong launch prompt. Better than "Give her a brief" if we commit to the
    sewing metaphor.
- "She stitched the run together."
  - Completion state.
- "A few seams worth checking."
  - Review prompt.
- "The thread held."
  - Successful run.
- "The thread broke."
  - Interrupted/browser failure. Use only if not too cute for the severity.
- "The good ones are pinned."
  - Review-ready state.
- "Pinned for judgment."
  - Stronger and less cute. Good candidate for saved candidates.
- "No loose threads."
  - Clean run.
- "A loose thread."
  - Soft issue/attention state.
- "The pattern is holding."
  - Strategy/search working.
- "The pattern needs altering."
  - Iteration/calibration needed.
- "Cut from the same cloth."
  - Calibration/fit.
- "Not quite the right cloth."
  - Weak match or rejection.
- "Measure twice, source once."
  - Brief/calibration line.
- "Hemmed, sorted, and ready."
  - Completion line; more decorative.

## Compilation / Evidence Language

Useful for keeping the product grounded in work, not magic.

- "She's compiling a shortlist."
  - Running state.
- "Compiled, not conjured."
  - Anti-AI-chrome line.
- "She kept the receipts."
  - Evidence/rationale/audit surface.
- "She made a few notes in the margin."
  - Rationale/detail surface.

## Wordplay

Use sparingly. These are seasoning, not structure.

- "Delusions of gran-deur."
  - Cleaner than "gran(ny)deur".
- "A modest act of gran-deur."
  - Softer section title.

## Suggested UI Mapping

These are not final. They are the current best-fit candidates by surface.

- Home hero, populated:
  - "She left the good ones on top."
- Home hero, idle:
  - "She'll tell you when there's something."
- Launch panel:
  - "Give her the pattern."
- Running state:
  - "Needlework, not guesswork."
  - "She's compiling a shortlist."
- Completed state:
  - "She stitched the run together."
  - "The thread held."
- Review state:
  - "The good ones are pinned."
  - "Pinned for judgment."
- Interrupted state:
  - Plain operational copy first.
  - Optional soft line only outside the error body: "The thread broke."
- Evidence/detail:
  - "She kept the receipts."
  - "She made a few notes in the margin."

## Open Questions

- Is the sewing/pattern metaphor the main product grammar, or just one surface?
- Should Cloris identify runs by brief/pattern names instead of raw state keys?
- Does "busybody" belong in product copy, or only internal prompt language?
- Should the main motion motif be needle/thread, paper/card, or stamp/ledger?
