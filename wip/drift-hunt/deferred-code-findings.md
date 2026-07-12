# Drift Hunt — deferred code findings

Defects the hunt surfaced whose fix belongs in **code**, not docs (Louis' Checkpoint 0 ruling, 2026-07-12: doc-side these are fine; code-side issues get deferred here rather than fixed mid-campaign). One entry per finding; pick these up as ordinary follow-ups after the campaign (or sooner if one becomes pressing).

## 1. `pipelex validate` shortcut forms are invisible in `--help`

**Found:** Stage 0, via the CLI pre-screen near-miss (see `suspects.md` FP pattern 8).

**Behavior:** `pipelex/cli/commands/validate/app.py` defines a custom click group whose `parse_args` rewrites `pipelex validate <pipe_code>` and `pipelex validate --all …` into `pipelex validate pipe …` — but the `--help`/`-h` path deliberately bypasses the rewrite, and the group's help output lists only the `method`/`pipe`/`bundle` subcommands with no mention of the shortcut. `docs/tools/cli/validate.md` documents the shortcut; the CLI's own help contradicts it.

**Why it matters:** any consumer that derives the command surface from `--help` (a human skimming, an agent, tooling like the hunt's pre-screen) concludes the documented forms are dead. That's exactly the false "confirmed defect" Stage 0 produced before live execution disproved it.

**Candidate fix (code):** surface the shortcut in the group help — e.g. an epilog/help line on the `validate` group ("`pipelex validate [PIPE_CODE|--all]` is a shortcut for `validate pipe …`"), or expose the forwarded options on the group so `--help` lists them. Keep the rewrite semantics unchanged; this is a help-surface fix only. Update `docs/tools/cli/validate.md` only if the chosen wording changes the documented contract.
