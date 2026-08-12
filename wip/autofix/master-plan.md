# Autofix — executive master plan

Deterministic auto-fixing of `.mthds` validation errors. Full rationale and architecture: [suggested-fixes-design.md](suggested-fixes-design.md). Approved decisions: fixes attach to validation diagnostics (D1), runtime-only wire first (D2), wave 1 targets agent CLI + skills (D3), pruning cut from wave 1 (D4).

**Guiding principle:** one validation engine feeds every surface. Validators state what they expected; a planner turns that into structured `suggested_fix` payloads on the report; appliers and commands are thin. Fix ops are contract, rendered diffs are presentation.

## Where we are

**Step 1 (spike) is DONE** — PR #1027 vs dev, merge-ready. The full chain is proven on one rule (`match-sequence-output`): enriched typed error → planner → tomlkit applier → convergence loop, all TDD, golden format-preservation tests pinning tomlkit's in-place style preservation. The `suggested_fix` payload already rides `pipelex-agent validate bundle --format json` and the `/validate` API 422 body, because the planner hooks into the one shared `build_validation_error_items` builder. Checkpoint findings are recorded in the design doc; deliberate deferrals in [deferred-checkpoint-0-review-items.md](deferred-checkpoint-0-review-items.md).

**Step 2 (wave-1 rule breadth) is DONE** — on the stacked branch `feature/Autofix-step2` (PR #1031). All three wave-1 rules landed, each a deliberately different fix *shape*: `sync-controller-inputs` (multi-op in-place table sync, Phase A), `strip-native-concept-redecl` (delete-shaped, first blueprint channel, Phase B), and the stretch `strip-namespace` (position-preserving rename, Phase C — **GO, shipped**). Mid-step, Phase A′ swapped the applier's hand-rolled canonicalization for the in-process `pipelex_tools.format_mthds` backend (core runtime dep). **Abstraction verdict (CHECKPOINT 1): `SuggestedFix`/`FixOp` survived all four shapes with no structural change** — the only wire-level edit was widening `TomlValue` (the type of `FixOp.value`) to admit a flat scalar dict; the feared array-of-tables `table_path` extension was never needed. Full verdict + carried-forward warts in the design doc's "Step-2 exit — abstraction verdict" section; per-checkpoint deferrals in `deferred-checkpoint-{a,a-prime,b,c,d}-review-items.md`. Reviewer's guide: [step2-reviewers-guide.md](step2-reviewers-guide.md) (archived from the worktree-root `TODOS.md`).

**Steps 3 (hardened loop) and 4 (agent apply surface) are DONE** — merged together as PR #1035 (`feature/Autofix-step4-Agnt-Apply`). Step 3 replaced the spike's drop-everything scoping guard with real multi-file targeting (source backfill at the translate funnel, resolved-dirs single-file gate, write-scope policy, per-file apply with `files_written`); step 4 shipped `pipelex-agent fix bundle` with the CLI-free markdown renderer and full test coverage. The PR review triage fixed two confirmed bugs and deferred one inert finding to [pr-1035-review-notes.md](pr-1035-review-notes.md).

**Step 5 (human CLI surfacing) is DONE** — `pipelex fix bundle` (including the `--diff` preview), the `💡 Suggested fix:` lines + actionable footer in `pipelex validate`, docs, and changelog all landed on branch `feature/Autofix-step5`; detailed plan + decisions: [step5-human-cli-surfacing.md](step5-human-cli-surfacing.md). The CHECKPOINT B exit review fixed five confirmed bugs on the branch and deferred five tradeoffs — triage in [deferred-checkpoint-e-review-items.md](deferred-checkpoint-e-review-items.md). The branch is PR-ready; **step 6 (release train) is next**, and its CHANGELOG must still name the additive `suggested_fix` wire field in `/validate` payloads (deferred item 1c) plus regenerate the cross-repo error-QA fixture (deferred item 2).

## Sequencing doctrine (decided 2026-07-07)

- **The agent surface is the proving ground.** Agent JSON output and tests are where the `SuggestedFix`/`FixOp` shape gets iterated freely — machine consumers we control, no format freeze. This is D3 operationalized.
- **The human CLI comes last in wave 1, gated on two testable bars** — not on a "complete fixer" (completeness is a moving target and invites big-bang scope):
  1. The abstraction has been stress-tested by rules of *different shapes* — not just another `set_key`, but in-place table sync and delete ops — so the wire shape and the `description` wording are known-stable before humans see them.
  2. The apply command exists, so a human-facing hint has an action behind it (`pipelex fix`), not a "go hand-edit this" teaser.
  Rationale: a `💡 Suggested fix` line that appears for exactly one error class reads worse than no hints at all, and anything shown to humans becomes user-facing output we can no longer reshape freely.
- **Known plumbing fact for the human step:** the human renderer (`_display_validation_error_details` in `pipelex/cli/error_handlers.py`) does NOT flow through `build_validation_error_items` — it iterates raw `PipesAndConceptValidationErrorData` and prints fields by hand. Surfacing fixes there is a deliberate addition (call the planner from the renderer, or route it through the shared items), not free-riding on existing wiring.

## Steps

### 1. Spike — prove the chain end-to-end — **DONE (PR #1027)**

One rule through all layers, no CLI command, driven by tests. Exit criteria met: chain proven, format preservation demonstrated by golden tests, design doc updated with findings. Reviewer's guide: [spike-reviewers-guide.md](spike-reviewers-guide.md).

### 2. Wave-1 rule breadth — stress the abstraction — **DONE (PR #1031)**

Detailed implementation plan with progress checkboxes: was `TODOS.md` at the worktree root, now archived as [step2-reviewers-guide.md](step2-reviewers-guide.md).

Add the remaining wave-1 rules, in this order (each is a different fix *shape*, which is the point):

- **`sync-controller-inputs`** — `MISSING_INPUT_VARIABLE` / `EXTRANEOUS_INPUT_VARIABLE` / `INPUT_STUFF_SPEC_MISMATCH` on a controller pipe → in-place sync of the `inputs` table with `needed_inputs()`. First non-`set_key` shape: multiple ops per fix, add/update/delete inside an existing table without rebuilding it (the old branch's rebuild destroyed comments/style). Carries the two rule guards from the design doc: **optionals markers** (preserve the author's `?`/`!` when concept+multiplicity already match; derive markers only for added inputs) and **prerequisite-clean** (suppress the fix when co-errors like `UNRESOLVED_PIPE_DEPENDENCY`/`UNRESOLVED_CONCEPT` on the same pipe make `needed_inputs()` untrustworthy — the loop picks it up next round).
- **`strip-native-concept-redecl`** — blueprint-level error for a redeclared native concept → `delete_table` / `delete_key` for `[concept.X]` or inline `concept.X = "..."`. First *blueprint-channel* fix (the spike only enriched the pipe-validation channel) and first delete-shaped fix in production.
- **`strip-namespace` (stretch)** — same-domain dotted pipe codes → position-preserving rename + rewrite of internal refs (`steps`, `branches`, `branch_pipe_code`, `outcomes`, `default_outcome`, `main_pipe`). Gated on **position-preserving rename mechanics** in tomlkit (the old branch's `del`+re-add reordering bug is the thing to avoid); if rename doesn't land clean, this rule stays out of wave 1. When rename lands, also add `new_key` to the loop fingerprint (deferred item 1b).

Exit (**CHECKPOINT 1**) — **met:** all wave-1 rules green with planner suppression tests + golden format-preservation tests; the explicit **abstraction verdict** is recorded in the design doc ("Step-2 exit — abstraction verdict") — `SuggestedFix`/`FixOp` survived multi-op, delete, blueprint-channel, **and** rename fixes with no structural change (only an additive `TomlValue` widening). **strip-namespace decision: GO — shipped** (position-preserving rename via tomlkit's `Container._replace`; `RENAME_TABLE_KEY` proven end-to-end; the array-of-tables `table_path` extension it was gated on turned out never to be needed).

### 3. Hardened loop — real multi-file targeting

Detailed design + working plan (shared with step 4): [step3-step4-hardened-loop-and-agent-apply.md](step3-step4-hardened-loop-and-agent-apply.md), on the stacked branch `feature/Autofix-step4-Agnt-Apply`.

Replaces the spike's conservative scoping guard (source-less fixes are simply dropped under `library_dirs`). Deferred items 0 and 1 from checkpoint 0:

- Thread the declaring file into enriched errors — set `file_path` or better yet `source` at the raise sites, so `SuggestedFix.source` is actually populated and the loop's file check stops being dead code.
- Derive `is_single_file` from the **resolved** effective dirs (`resolve_library_dirs`), fixing both wrong directions of the current raw-arg check (`[]` is documented single-file but treated as multi; `None` can fall through to hub defaults/`PIPELEXPATH` and load other files while being treated as single).

Ships behind CHECKPOINT 1. Exit: fixes apply correctly across multi-file bundles, targeting the declaring file only; the drop-everything guard is gone.

### 4. Agent apply surface — `pipelex-agent fix bundle`

Detailed design + working plan (shared with step 3): [step3-step4-hardened-loop-and-agent-apply.md](step3-step4-hardened-loop-and-agent-apply.md).

Thin command over `fix_bundle_file`: two-stream output per the workspace output conventions (`--format`/`--error-format`, JSON contract carrying `FixBundleResult` — is_valid, iterations, fixes_applied, remaining_errors, bail_reason; markdown rendering for the agent as presentation). e2e CLI snapshot tests. This is the milestone where an agent can run validate → fix → re-validate entirely from the CLI. Exit: command shipped on the agent CLI, snapshots green.

### 5. Human CLI surfacing — gated on steps 2 + 4 — **DONE (branch `feature/Autofix-step5`, PR-ready)**

Detailed implementation plan with progress checkboxes: [step5-human-cli-surfacing.md](step5-human-cli-surfacing.md). Checkpoint B triage: [deferred-checkpoint-e-review-items.md](deferred-checkpoint-e-review-items.md).

Both gates from the sequencing doctrine are now met. Two pieces, landed together for symmetry:

- `pipelex fix` (human command) wrapping the same loop with human-rendered output.
- `💡 Suggested fix:` line per fixable error in `pipelex validate`'s error rendering (via the planner from the human renderer path — see plumbing fact above), showing `SuggestedFix.description` only (ops stay machine-facing).

Exit: a human can see the suggestion in `validate` and apply it with `fix`, with output that names every change made.

### 6. Ship wave 1

Release train: CHANGELOG entry (must mention the **additive `suggested_fix` wire field** now surfacing in `/validate` API payloads — deferred item 1c — plus the new commands), docs page in `docs/`, cut the pipelex release. Post-release follow-through: regenerate the fixture in our cross-repo spec suite that pins the `/validate` error body (deferred item 2) and bump the pipelex-api pin when the runner picks the version up. Exit (**CHECKPOINT 2**): released; hand-off list for wave 2 recorded.

### 7. Skills uptake

Update the `mthds-fix` skill (and the pipelex-plugins equivalent) to run deterministic `fix` before manual LLM editing. Cross-repo, cheap, gated on step 6's release.

### 8–10. Wave 2 (each gets its own plan when it starts)

- **Protocol promotion**: `suggested_fix` becomes a formal MTHDS protocol surface — protocol-spec sections, a cross-repo spec-suite arm, schema sync to downstream copies (mthds, mthds-js, mthds-python).
- **Remote surfaces**: API `POST /fix` on pipelex-api, MCP `mthds_fix` tool — thin wrappers over the same engine/report; the markdown renderer already lives CLI-free for this reason.
- **Editor**: VS Code `CodeActionProvider` (first code action in the extension), quick fixes keyed on `diag.code = error_type` with fix payloads riding the existing validation backends.

These are independent of each other once wave 1 has shipped and can be re-prioritized freely.

### Later

Pruning rules (`prune-unreachable`, `prune-unused-concepts`) resurrected as opt-in lint warnings with attached fixes (D4 — they're cleanups, not fixes); further rules as validator enrichment makes them deterministic.

## Sequencing summary

Step 2 → 3 → 4 are the wave-1 engine-and-agent track and land in that order (3 may overlap 2). Step 5 is deliberately gated on 2 + 4, never earlier. Step 6 ships the lot; 7 follows the release. Each step gets its own detailed TODOS-style plan when it starts — this document stays the map.
