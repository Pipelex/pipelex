# Step F deferred notes

Deferred items surfaced while writing the Step F specs, spec-suite coverage and docs. Same policy as the other deferred docs in this folder: none of these block phase 1; triage them with the cross-repo wave or on demand.

## Pre-existing: inline `$var` followed by ` (` escapes template variable detection

Found while ground-truthing the `optional_input_unguarded` spec-suite fixture. A prompt like `"Greet $name (nickname: $nickname)."` reports `extraneous_input_variable` for `name` — the inline `$name` reference is not detected as a variable use when it is immediately followed by a space and an opening parenthesis. `"Greet $name today, nickname: $nickname."` detects both fine. Most likely the preprocessed Jinja2 parses `name (…)` as a call expression, and the variable walker misses the callee (or the detection regex swallows the call shape). Pre-existing behavior, unrelated to optionals — reproduced with plain (non-optional) inputs too. Worth a small fix in the variable-detection walk (`jinja2` dissection utilities); the workaround is any other punctuation/wording between the variable and the parenthesis.

## Spec-suite optionals coverage was pinned ahead of the runtime — gates removed at release

**DONE** (pipelex 0.38.0 + pipelex-api 0.8.0). Our cross-repo spec suite had written its optionals coverage against an unreleased runtime and gated all of it behind a pending-feature marker; the gate-removal checklist was executed against the released runtimes, and every optionals QA case, categorized row and warnings test now runs ungated on both arms (agent-CLI and hosted HTTP), zero skips. The generic gating infrastructure was kept as dormant, reusable machinery — it is independently tested and still live for another pending-feature gate. The step-by-step execution record lives at workspace level with the rest of that suite's notes.

The same 0.35→0.38 pin bump also swept up the **PipeSignature-tag retirement** (0.38.0 rejects `type = "PipeSignature"` — `unknown_pipe_type`, "no longer a pipe type"; a signature is now a **type-less** pipe, no `type` and no implementation), plus benign wording refreshes in a few unrelated corpus cases (verdict/category/error_type unchanged). The shipped verdict contract was confirmed and kept: a pending signature is `is_valid=true` in BOTH strict and `--allow-signatures` modes, gated only via exit code (strict→1, `--allow-signatures`→0) — `is_valid` ≠ `is_runnable`.

Open follow-ups surfaced (NOT done here — flagged to route):

- **plxt/vscode-pipelex schema propagation.** pipelex 0.38.0's regenerated schema DOES carry `PipeSignatureBlueprint` (type-less, no required `type`), but the plxt-bundled schema is stale and rejects type-less bundles — an `mthds-schema-sync` propagation item (cross-repo wave).
- **The `pipelex#996` QA gate is now stale.** 0.38.0 emits `blueprint_validation / batch_item_name_collision` structured, so the batch-item-collision case's pending-feature gate is dormant; per the marker-removal policy it should be dropped to close the invisible-regression window.
- **`-L` directory-load path drops structured `error_type` for static-pass validators.** `library_manager.py:824` (`except ValidationError`) stringifies static-pass `PipeValidationError`s (e.g. `optional_output_required`, `optional_input_unguarded`) instead of categorizing them, so a `-L`-loaded bundle degrades to an uncategorized `blueprint_validation` residual — whereas single-file CLI and HTTP `mthds_contents` both categorize correctly. Latent pipelex bug (pre-existing, predates optionals), independent of this task.

## PipeBatch compaction does not ledger the dropped branches (PipeParallel does)

Surfaced by the Step F cold review. When PipeBatch compacts an absent branch result out of the aggregated list (`pipe_batch.py`, the `AbsenceRecord` arm of the aggregation loop), it only emits a `log.verbose` line — unlike PipeParallel, which calls `working_memory.record_resolved_absence` for an omitted composite component. So a run's absence ledger does not show which batch items were dropped. Design question, not a bug: N dropped branches would add N records (noisy for large batches), and the compacted list itself is a present value at the boundary. If ledger parity is wanted (e.g. for the route-or-skip auditing story), record one absence per dropped branch (or one summarizing record) into the parent working memory during aggregation. Revisit with phase 2 observability work.

## Absence records on the hosted wire — the spec-suite pin awaits the mthds bump

The spec section "Absence records on run artifacts" is `<!-- unverified -->` by design: the hosted `/v1/execute` cannot return the `absences` ledger until the mthds SDK wire models can carry it (cross-repo hand-off item 1 in the tracker). When that lands, add an HTTP-arm test to our cross-repo spec suite (a PipeFunc/PipeCondition-only bundle whose optional output resolves absent) and flip the spec section to `> Verified by:`.
