# keyword-only-arguments

Track record for the **keyword-only arguments refactor** on `refactor/Function-calling-4`: every non-subject parameter across `pipelex/` source is now keyword-only, mechanically enforced by the `check-keyword-only` AST guard (in `make agent-check`, `make check`, and CI).

## Status

The pipelex-internal refactor is **complete and landed on the branch** — all waves done, the guard hard-blocks on any violation, and the convention is promoted to the canonical contributor doc at [`docs/contribute/keyword-only-arguments.md`](../../docs/contribute/keyword-only-arguments.md) (in the mkdocs nav). The downstream consumers were updated in lockstep (PRs #19 / #55 / #75 / #153, plus pipelex-worker #23) and **pushed**, all pinned to the branch git rev `0e32c8c0` and green on their test suites. (`pipelex-mistralai-workflows` is the one genuine out-of-scope consumer — it's on its own mistralai-2x hold track.)

**One open item:** at pipelex release, swap each consumer's temporary `[tool.uv.sources]` git pin back to the released `pipelex` version. Tracked in the checklist of [`downstream-consumer-breakage.md`](downstream-consumer-breakage.md).

## What's here

- **[keyword-only-arguments.html](keyword-only-arguments.html)** — self-contained co-developer explainer: TL;DR, what/why, the rule, how it was enforced, the audit→consolidation→downstream-fix arc, and minimal diffs for the critical changes. Open in a browser.
- **[downstream-consumer-breakage.md](downstream-consumer-breakage.md)** — the living cross-repo lockstep record. Which consumer call sites broke at each pipelex SHA, how each was fixed, and the at-release pin-swap checklist. This is the one doc with an open action.
- **[positional-subject-suspects.md](positional-subject-suspects.md)** — RESOLVED. The consolidated shortlist of 59 "positional-subject abuse" suspects (functions that kept their subject positional only to satisfy the carve-out) and the adjudication that turned them all fully keyword-only.
- **audit/** — raw process artifacts from the positional-subject audit (reference, not active):
    - [`positional-subject-audit.md`](audit/positional-subject-audit.md) — the full machine+LLM audit of every audited function (large).
    - [`review-prompt.md`](audit/review-prompt.md) — the sub-agent review prompt that drove the audit.
    - [`findings/`](audit/findings/) — per-package suspect shortlists, one file per `pipelex/` package.
