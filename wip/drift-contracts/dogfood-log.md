# Drift-contracts dogfood log

One entry per ack. Verdicts: **real-catch** (the review found actual staleness), **clean-pass** (genuinely reviewed, nothing was stale), **friction** (the contract opened on changes that could not have affected the targets — candidate for narrowing or mechanizing).

- **2026-07-10 · keyword-only-convention · real-catch** — the guard gained the subject-grant registry (new violation kinds, literal-subject ban, symmetric staleness); the convention doc was materially stale and was rewritten as part of the same change — exactly the coupling this contract exists to enforce.
- **2026-07-10 · cli-docs · clean-pass** — the keyword-only sweep touched many pipelex/cli files (kwonly'd internal signatures, two escape hatches, call-site keywords); reviewed docs/tools/cli/ and the agent-CLI CLAUDE.md — no command, flag, or output changed, both targets stay accurate.
