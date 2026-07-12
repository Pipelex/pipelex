# Drift Hunt — deferred code findings

Defects the hunt surfaced whose fix belongs in **code**, not docs (Louis' Checkpoint 0 ruling, 2026-07-12: doc-side these are fine; code-side issues get deferred here rather than fixed mid-campaign). One entry per finding; pick these up as ordinary follow-ups after the campaign (or sooner if one becomes pressing).

## 1. `pipelex validate` shortcut forms are invisible in `--help`

**Found:** Stage 0, via the CLI pre-screen near-miss (see `suspects.md` FP pattern 8).

**Behavior:** `pipelex/cli/commands/validate/app.py` defines a custom click group whose `parse_args` rewrites `pipelex validate <pipe_code>` and `pipelex validate --all …` into `pipelex validate pipe …` — but the `--help`/`-h` path deliberately bypasses the rewrite, and the group's help output lists only the `method`/`pipe`/`bundle` subcommands with no mention of the shortcut. `docs/tools/cli/validate.md` documents the shortcut; the CLI's own help contradicts it.

**Why it matters:** any consumer that derives the command surface from `--help` (a human skimming, an agent, tooling like the hunt's pre-screen) concludes the documented forms are dead. That's exactly the false "confirmed defect" Stage 0 produced before live execution disproved it.

**Candidate fix (code):** surface the shortcut in the group help — e.g. an epilog/help line on the `validate` group ("`pipelex validate [PIPE_CODE|--all]` is a shortcut for `validate pipe …`"), or expose the forwarded options on the group so `--help` lists them. Keep the rewrite semantics unchanged; this is a help-surface fix only. Update `docs/tools/cli/validate.md` only if the chosen wording changes the documented contract.

## 2. `plxt lint` does not detect invalid concept references (cross-repo: `vscode-pipelex`)

**Found:** Stage 1 Part 3, as the code side of finding F10 (`docs/features/plxt.md:24`).

**Behavior:** `plxt lint` (v0.6.0) is a pure JSON-Schema structural validation pass (required / type / enum / additionalProperties) plus a type-discriminated per-pipe-blueprint check. There is **no cross-reference resolution step**, so a `.mthds` file referencing a concept that was never declared lints **clean**: `output = "NonExistentConcept"` → exit 0, no diagnostics; `inputs = { topic = "TotallyMadeUpConcept" }` → exit 0. (Control: an unknown *pipe type* IS caught — `error[schema]: "UnknownPipeType" is not one of [...]`, exit 1.) The only concept-reference resolution in the toolchain is `crates/taplo-lsp/src/handlers/mthds_resolution.rs`, which is LSP-only (hover / goto-definition) and emits no diagnostic; `taplo-lsp/src/diagnostics.rs` has no concept logic at all.

**Why it matters:** it is a capability gap, not a bug — but the docs promised it, which is what makes it worth recording. Undefined concept references are caught today only by `pipelex validate`, i.e. only once a human/agent reaches for the runtime. A fast, editor-time diagnostic is exactly what the linter is for.

**Doc-side (in scope, Stage 2):** drop "or invalid concept references" from `docs/features/plxt.md:24` — the claim is currently false. That fix stands on its own and does **not** depend on the code side.

**Candidate fix (code, other repo — `vscode-pipelex`):** add a concept cross-reference resolution pass to the lint path, reusing the resolution logic that already exists for the LSP, and surface it as a diagnostic in both `plxt lint` and the LSP. Out of scope for this campaign (D8: another repo's code); hand off to the toolchain owner. If the team decides `plxt lint` should stay purely structural, then the doc fix is the *whole* fix — and that is a legitimate outcome.
