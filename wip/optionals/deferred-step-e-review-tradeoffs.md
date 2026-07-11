# Deferred design tradeoffs from the Checkpoint E cold review

Findings from the Checkpoint E cold review that are deliberate scoping choices, cross-repo-gated work, or pre-existing sharp edges the diff newly exposed — not silent bugs introduced by Step E. Each entry records the finding, why it is deferred, and what would trigger picking it up. (Correctness and consistency findings from the same review were fixed in the checkpoint follow-up commit: the lifted-plural producer registration in both graph builders, the useless-`!` lint wired into the bare CLI and the builder validate_ops twins, the single shared taint walk per validate pass, the shared `output_digest_is_optional` helper, the shared absence JSON/HTML renderers, and the docs for the new graph and validate surfaces.)

## 1. API-runner run path errors on a designed absence (cross-repo gated)

`pipelex-agent run --runner api` raises a "runner contract violation" `PipeExecutionError` when the main output legitimately resolved absent, because the mthds SDK wire model (`DictWorkingMemoryAbstract`, `extra="forbid"`, root + aliases only) cannot carry the absences ledger — so the CLI cannot distinguish a designed absence from a genuinely missing output. The local runner renders a first-class absence document for the same run.

**Why deferred:** fixing it requires the mthds SDK (and the API response models) to carry `absences` on the wire — a cross-repo protocol bump already listed in the tracker's cross-repo hand-off notes. Guessing "absent" from a missing key without the ledger would erase provenance and mask real contract bugs.

**Pick up when:** the mthds SDK working-memory model gains the `absences` field; then implement the absent arm in `_run_core_api.py` (mirror `_run_core.py`'s absence document) and add the API-arm test.

## 2. Builder-generated runner code crashes on an absent optional output (pre-existing, newly exposed)

`pipelex/builder/runner_code.py` scaffolds example scripts that read `pipe_output.main_stuff` / `main_stuff_as(...)` unconditionally. For a pipe with a declared-optional output whose run resolves absent, the generated script dies in `get_main_stuff` (the ledger is not consulted) while every in-repo surface renders an absence document.

**Why deferred:** builder codegen is the spec/authoring layer — making the generated snippet absence-aware (branch on `resolve_main_stuff()`, print the absence summary) is an authoring-UX design choice that belongs with the builder-layer optionals pass, not a one-line patch inside a checkpoint triage.

**Pick up when:** the optionals track reaches the builder/spec layer (specs learn `?`/`!`), or the first user report of a scaffolded script crashing on a designed absence.

## 3. `{{ var | length }}` on singular content still raises (pre-existing sharp edge)

`StuffArtefact.__bool__` fixed the `{% if var %}` truth test, but `__len__` still raises `TypeError` for non-list content, and Jinja2's `length` filter is the `len()` builtin — so `{{ var | length }}` (or `{% if var|length > 0 %}`) on a PRESENT singular value raises the very error the `__bool__` fix targets.

**Why deferred:** giving singular content a `__len__` invents a semantic (1? character count?) that would silently change template behavior far beyond optionals; D4 keeps length a list concept. The truthiness idiom (`{% if var %}`) is the documented guard shape and works on both arms.

**Pick up when:** real bundles hit `|length` on singular optionals — then extend the template guard-lint to flag `|length` applied to a singular slot and point at the truthiness idiom instead (lint, not semantics).

## 4. `GraphTracerManager.add_edge` facade does not expose `optional` (latent)

The tracer-level `add_edge` carries `optional`, but no current caller routes explicit edges through the manager facade with that flag — reviewer-confirmed latent, no behavior impact today.

**Why deferred:** dead parameter-plumbing until a controller actually emits an explicit optional edge; the DATA-edge path (where `optional` is computed) does not go through the facade.

**Pick up when:** a controller needs to emit an explicit edge with the optional marker — extend the facade signature then.

## 5. No OTel span for lifted leaf pipes (pre-existing)

A lifted pipe returns from `run_pipe` before the operator-level OTel span factory runs, so a skipped leaf emits no span at all (the graph, ledger, and parent spans still record the skip). Pre-existing behavior untouched by Step E; the new absence-aware OTel code covers live-run pipes with absent optional inputs/outputs.

**Why deferred:** emitting a dedicated "skipped" span changes the telemetry shape and belongs with a deliberate observability design pass, not a triage patch.

**Pick up when:** operators report needing per-skip spans for tracing dashboards (the graph's `SKIPPED` node + `skip_reason` covers today's "why did this produce nothing?" question).

## 6. Deeper taint-walk memoization still open (carried from Step D)

Step E's triage collapsed the two validate-report projections onto one `collect_controller_taint_analyses` pass, but a controller's analysis can still run again inside `validate_output_with_library` and inside an enclosing controller's walk (Step D deferred item 2). Same reasoning, unchanged: validation-time only, no measured pain — profile before memoizing.
