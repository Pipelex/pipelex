# TODOS — Required main stuff (PipeParallel always combines)

**Branch:** `feature/Required-main-stuff` · **Design:** `wip/required-main-stuff.md` (full) · `wip/required-main-stuff-brief.html` (brief)

**Scope:** implement the design **excluding §9 (companion track — `/execute` vs `/start`→delivery result-shape unification)**, which is designed and tackled separately. Everything else is in scope: always-combine `PipeParallel`, delete `combined_output`, new `native.Composite` concept, static branch-name validation, invariant enforcement across in-repo surfaces, then the gated cross-repo sweep.

## The rule being implemented

> A pipe run always delivers a main stuff. Consequently, a pipeline always delivers a main stuff.

Enforced at the one non-stamping leaf: `PipeParallel` always combines its branch outputs into its declared `output` concept and stamps that as main stuff. `combined_output` is deleted (breaking, no back-compat per house policy). `native.Composite` is the untyped combination vehicle.

## Working conventions for this track

- **TDD:** write the red tests first for each behavioral change, then implement to green.
- **Gates:** `make agent-check` after code changes; targeted pytest during development (`.venv/bin/pytest -x -q <path>`); full `make agent-test` before each checkpoint.
- **Commits:** one commit per phase, landed at its checkpoint, so each review sub-agent gets a clean SHA range.
- **Checkpoint protocol (MANDATORY STOP):** at each checkpoint the agent must stop forward progress and, in order:
  1. **Verify** — run the phase's full gates (`make agent-check` + `make agent-test`) and confirm the phase's acceptance criteria below.
  2. **Update this file** — check off done items, record decisions taken, deviations from the design, and current code state in the "Checkpoint log" section, so a brand-new session can cold-start from this file alone. Update `wip/required-main-stuff.md` status line too.
  3. **Fan out review** — spawn a **Sonnet-5 sub-agent with NO inherited context** to run the `/code-review` skill on the phase's changes. Hand it *only* a pointer to the changes (the phase's commit SHA range, e.g. `git diff <base>..HEAD`, or the working-tree diff) — never the plan, the design doc, the rationale, or your own conclusions. Target: clean solid software, not over-engineering.
  4. **Triage findings** — fix real defects before proceeding; findings that are design tradeoffs (not silent bugs) go to a deferred-items doc under `wip/required-main-stuff/`, not reflexively applied.

## Phase 1 — Runtime + language surface (this repo)

### 1a. Red tests first

- [x] Regression test for the **stale-stamp bug**: a `PipeSequence` ending in an `add_each`-only `PipeParallel` must deliver the combined composite as main stuff, not the previous step's output (today it silently delivers step N-1's stuff).
- [x] **Terminal-parallel delivers main stuff**: an `add_each`-only parallel as top-level `main_pipe` with memory from `make_from_pipeline_inputs` (the API path) completes with a stamped main stuff (today `main_stuff_name` is `None` and `PipeOutput.main_stuff` raises).
- [x] **Static validation accept/reject cases**: `output = "Composite"` accepted; structured concept with fields matching branch `result` names accepted (required fields ⊆ result names, result names ⊆ declared fields); native non-composite (`Text`, `Image`, …), `Dynamic`, `Anything`, and multiplicity suffixes (`Foo[]`, `Foo[N]`) rejected at bundle/library validation time.
- [x] **`CompositeContent` round-trips**: `smart_dump`, kajson transport round-trip (`dump_for_transport` → rehydrate), `rendered_markdown` / `rendered_html` with named sub-contents surfaced as top-level fields (no wrapper key).
- [x] **Dry-run parity**: dry run of a parallel stamps the same combined main stuff shape as live run.

### 1b. `native.Composite` concept

- [x] Add `COMPOSITE = "Composite"` to `NativeConceptCode` in `pipelex/core/concepts/native/concept_native.py`.
- [x] New `CompositeContent(StuffContent)` in `pipelex/core/stuffs/composite_content.py` — pydantic `extra="allow"` so branch names are top-level serialized fields; full content surface (`smart_dump`, kajson round-trip, `rendered_markdown`/`rendered_html`).
- [x] Register in the class registry + concept factory wherever native concepts are wired.

### 1c. Always-combine runtime

- [x] `pipelex/pipe_controllers/parallel/pipe_parallel.py`: unconditional combine in `_live_run_controller_pipe` **and** `_dry_run_controller_pipe` via a shared helper (an existing TODO already asks for this); combination concept taken from `self.output`; `set_new_main_stuff` always called; parallel-combine graph edges always registered.
- [x] Investigate `final_stuff_code` while in this file (the parallel currently clears it with a copy-pasted `PipeBatch` log line): confirm what it drives (graph/trace identity) — final wiring decision is a Phase 2 item, but capture findings now.

### 1d. Delete `combined_output` across the language surface

- [x] `pipelex/pipe_controllers/parallel/pipe_parallel_blueprint.py`: delete field + the one-of-two (`add_each_output`/`combined_output`) validator.
- [x] `pipelex/pipe_controllers/parallel/pipe_parallel_factory.py`: stop resolving the combined concept separately.
- [x] `pipelex/builder/pipe/pipe_parallel_spec.py`: delete field + validators; simplify `to_blueprint()`; update pretty-render.
- [x] `pipelex/builder/operations/pipe_ops.py` + `pipelex/cli/agent_cli/commands/pipe_cmd.py`: remove `combined_output` display/handling code.
- [x] `pipelex/core/bundles/pipelex_bundle_blueprint.py`: drop the `combined_output` concept-ref collection; **add the new static structure-compatibility check** (design §3).

### 1e. Fixtures, schema, docs

- [x] Migrate test fixtures and data: `tests/integration/pipelex/pipes/controller/pipe_parallel/pipe_parallel_1.mthds`, `tests/e2e/pipelex/pipes/pipe_controller/pipe_parallel/parallel_graph_*.mthds`, `tests/unit/pipelex/pipe_controllers/parallel/{data.py,test_pipe_parallel_blueprint.py}`, `tests/unit/pipelex/builder/pipe/pipe_controller/pipe_parallel/test_data.py`, `tests/unit/pipelex/builder/operations/test_pipe_spec_to_toml.py`, `tests/unit/pipelex/graph/test_mermaidflow.py`, `tests/integration/pipelex/pipeline/test_bundle_validator.py`, `tests/integration/pipelex/cli/test_agent_validate_pipe_in_bundle.py`, `tests/integration/pipelex/pipes/controller/pipe_parallel/test_pipe_parallel_validation.py` (and any others `grep -rln combined_output` surfaces).
- [x] Regenerate the MTHDS JSON Schema: `.venv/bin/pipelex-dev generate-mthds-schema`.
- [x] Rewrite `docs/building-methods/pipes/pipe-controllers/PipeParallel.md` to the new semantics — current reality only, no historical narrative.
- [x] Changelog entry under `[Unreleased]`, marked breaking (delete `combined_output`; `output` is the combination concept; new `native.Composite`).
- [x] Gates: `make agent-check` green, targeted parallel/builder/graph tests green, full `make agent-test` green.

### ⛔ CHECKPOINT 1 — MANDATORY STOP

Acceptance: parallel always combines (live + dry), `combined_output` fully gone from source and fixtures, `native.Composite` round-trips, static validation catches bad `output` declarations at `/validate` time, all gates green.

- [x] Verify acceptance criteria + full gates (`make agent-check` + full `make agent-test` green).
- [x] Commit Phase 1 — `757146324` on top of `1b26b3fae`.
- [x] Update this file (checkpoint log below) + design doc status for cold start.
- [x] Fan out context-free Sonnet-5 `/code-review` sub-agent on the Phase 1 diff (pointer only).
- [x] Triage findings: review found NO correctness bugs; duplicated native-concept match extracted to `NativeConceptCode.is_composite` (fixed); double-parse finding deferred → `wip/required-main-stuff/deferred-phase-1-review.md`.

## Phase 2 — Enforce the invariant across in-repo surfaces

Once every pipe stamps, "a completed run has a main stuff" is guaranteed; tighten the defensive branches from optional to direct.

- [x] Graph tracer output-spec branch in `pipelex/core/pipes/pipe_abstract.py` — remove the defensive branch and its apologetic comment ("main_stuff may not exist for pipes like PipeParallel…").
- [x] Delivery executor `pipelex/pipe_run/delivery_executor.py`: always write the `main_stuff.*` artifact files for completed runs (kills the "empty envelope" failure mode).
- [x] CLI run cores: `pipelex/cli/commands/run/_run_core.py` + `pipelex/cli/agent_cli/commands/run/_run_core.py` — drop the "no main output produced" branches for live runs.
- [x] OTel telemetry attribute extraction: `pipelex/system/telemetry/otel_factory.py`.
- [x] Wire models go non-optional (`main_stuff_name: str`): `pipelex/runtime_bridge/payloads.py`, `pipelex/runtime_bridge/serialization.py` (`resolve_main_stuff_root_key`), `pipelex/pipeline/pipeline_response.py` (`PipelexRunResultExecute`), `pipelex/cli/agent_cli/commands/run/_run_core_api.py`. Temporal payload history is not a concern — never shipped to prod.
- [x] Audit every remaining `get_optional_main_stuff` call site: `WorkingMemory.get_optional_main_stuff` itself **stays** (pre-run/empty memory legitimately has none); each post-run boundary call site is either tightened or justified in the checkpoint log.
- [x] Resolve the **`final_stuff_code`** open question (design §7) using the Phase 1c findings: presumably honor it on the combined stuff like operators do.
- [x] Gates: `make agent-check` + full `make agent-test` green.

### ⛔ CHECKPOINT 2 — MANDATORY STOP

Acceptance: no defensive main-stuff branch left for completed live runs; wire `main_stuff_name` non-optional; call-site audit documented; all gates green. Cross-repo work starts fresh from here — this checkpoint's TODOS update is the cold-start context for that session.

- [x] Verify acceptance criteria + full gates.
- [x] Commit Phase 2 — `3c3cf4570` on top of `9acbd7a86`.
- [x] Update this file (checkpoint log: final call-site audit results, `final_stuff_code` decision) + design doc status.
- [x] Fan out context-free Sonnet-5 `/code-review` sub-agent on the Phase 2 diff (pointer only).
- [x] Triage findings: ONE confirmed bug (reproduced by the reviewer) — `PipeCondition`'s `continue` outcome doesn't stamp a main stuff, so the tightened tracer epilogue crashed with a raw `WorkingMemoryStuffNotFoundError` whenever a condition continued with no pre-existing main stuff under active tracing. FIXED at the semantic site (see Checkpoint 2 log "Review triage"). All other tightened surfaces judged internally consistent by the review; no simplification findings.

## Phase 3 — Cross-repo sweep (GATED)

**Gate: do not start before Phases 1–2 are merged to `main` and a pipelex version is cut.** Each repo below is its own git repo — commit/PR per its own conventions.

- [ ] `mthds/` — spec: `mthds-format.md`, `pipes-controllers.md`, `validation-rules.md`, `namespace-resolution.md`, `cross-package-references.md`, `docs/mthds_schema.json` — remove `combined_output`, define always-combine + `native.Composite`.
- [ ] `vscode-pipelex/` — pinned `mthds_schema.json` in taplo-common; `plxt` lint/format accepts the new shape and rejects `combined_output`.
- [ ] `conformance/` — `tests/pipelex/test_validate_subcommands.py` fixture updates; keep spec ↔ test links green (`make check-spec-links`).
- [ ] `mthds-plugins/` — skills references: `mthds-reference.md`, `build-phases.md`, `recursive-cheat-sheet.md`, `mthds-run/SKILL.md` across plugin variants.
- [ ] `pipelex-app/` — `src/types/core/pipes/pipe_controllers/pipe-parallel.ts`.
- [ ] `mthds-ui/` — `src/graph/types.ts`: `combined_output_concept` exec-data key (kept as-is in Phase 1 for compat; decide rename here per design §7) + graph-spec data fixtures.
- [ ] `cocode/` — migrate `ai_instruction_update.mthds`, `swe_docs.mthds`.
- [ ] `pipelex-website/` — `docs/mthds-doc.md`.
- [ ] Demo/workshop repos — `illustration_generator/bundle.mthds` copies.
- [ ] SDKs (`pipelex-sdk-js/`, `mthds-python/`) + `pipelex-starter-python/` — tighten `main_stuff` handling for completed runs; check `PipeOutputAbstract` (mthds-python) for encoded main-stuff optionality (design §7). Full `find_main_content` cleanup also needs the companion track — do only the invariant-side tightening here.

### ⛔ CHECKPOINT 3 — MANDATORY STOP

Acceptance: every consumer repo aligned with the released pipelex version; conformance + spec-links green; no repo still references `combined_output`.

- [ ] Verify per-repo test suites / checks.
- [ ] Update this file; close out or fold residual items into follow-up trackers.
- [ ] Fan out context-free Sonnet-5 `/code-review` sub-agents per changed repo (pointer only — the repo's diff/SHA range).
- [ ] Triage findings; then close this track (companion track remains open, separate design).

## Open questions (from design §7 — resolve during implementation)

- [x] `final_stuff_code`: RESOLVED in Phase 2 — the parallel honors it on the combined stuff (see Checkpoint 2 log).
- [ ] Graph `execution_data` key `combined_output_concept`: keep name in Phase 1 for `mthds-ui` compat; rename decision in Phase 3 (`mthds-ui` row).
- [ ] `add_each_output` naming: recommendation is **keep** (pure churn otherwise); revisit only if MTHDS spec editors want it (Phase 3, `mthds/` row).
- [ ] `PipeOutputAbstract` (mthds-python): check for encoded optionality (Phase 3, SDKs row).

## Checkpoint log

*(Filled in at each checkpoint — decisions taken, deviations from design, current code state, audit results. This section is the cold-start context for a fresh session.)*

### Checkpoint 1 — reached (Phase 1 complete)

**Code state:** Phase 1 fully implemented on `feature/Required-main-stuff`; one commit carries the whole phase (see git log). `make agent-check` green; full `make agent-test` green.

**What landed:**

- `native.Composite`: `NativeConceptCode.COMPOSITE` + `CompositeContent(StuffContent)` (`pipelex/core/stuffs/composite_content.py`, pydantic `extra="allow"`), wired into `ConceptFactory.make_native_concept`, `NativeConceptCode.structure_class`, and `CoreRegistryModels.STUFF`. Custom `rendered_markdown`/`rendered_html` iterate the named components; a `components` property exposes `model_extra`.
- Always-combine runtime: `PipeParallel._run_branches_and_combine` is the shared live/dry helper (resolves the old TODO); combine concept comes from `self.output`; `set_new_main_stuff` and PARALLEL_COMBINE graph edges are unconditional. `combined_output` field deleted from runtime model, blueprint, factory, spec, pipe_ops/pipe_cmd display, and bundle-blueprint concept-ref collection.
- Static validation, two layers: (1) parse-time in `PipeParallelBlueprint.validate_output` — rejects multiplicity suffixes and native non-`Composite`/`Dynamic`/`Anything` outputs; mirrored on the runtime model in `PipeParallel.validate_output_static` for direct constructions; (2) library-time in `PipeParallel.validate_output_with_library` — structure-compatibility check (required fields ⊆ result names; result names ⊆ declared fields; `CompositeContent` subclasses skip). Both feed `/validate` (bundle parse + `Library.validate...` → `pipe.validate_with_libraries()`).

**Decisions / deviations from the plan:**

- The TODOS 1d line said to put the structure-compatibility check in `pipelex_bundle_blueprint.py`; it lives on `PipeParallel.validate_output_with_library` instead, because the concept's structure class (registered Python class, generated class, refines chain) is only resolvable against the loaded library — the bundle blueprint cannot see class-backed structures. Design §3 says "bundle/library validation time", which this satisfies.
- kajson round-trip needed a `__json_encode__` hook on `CompositeContent`: pydantic stores extras outside `__dict__`, so kajson's default `__dict__` fallback silently dropped every component. The hook hands kajson the live components so nested contents keep their class metadata (`# noqa: PLW3201` — kajson protocol name).
- A description-only concept as a parallel output is rejected by the field-compat check naturally (its generated structure class is TextContent-derived, requiring `text`), with a message suggesting `Composite` — test pins this.
- Graph `execution_data` key `combined_output_concept` kept (now always set = declared output concept ref) for `mthds-ui` compat, per design §7; rename decision deferred to Phase 3.
- `tests/e2e/.../cv_job_match.mthds` had two parallels with now-invalid outputs (`Page[]`, `Text`) — migrated to `Composite` (was not on the plan's fixture list).
- Mermaidflow unit test's IOSpec name `combined_output` renamed `combined_result` (terminology hygiene only — it was never the field).

**`final_stuff_code` findings (1c investigation, wiring decision = Phase 2):**

- Producer: only `PipeBatch` sets it — a pre-allocated per-branch stuff code (`branch_output_item_code`) so the batch's aggregated `ListContent` item identity matches the branch's final output stuff in the graph.
- Consumers: `PipeLLM` and `PipeStructure` pass it as `code=` to `StuffFactory.make_stuff` for their output stuff. Other operators do not honor it (pre-existing gap worth noting in Phase 2).
- `PipeSequence` threads it to the last step only (clears for earlier steps); `PipeBatch` and `PipeParallel` clear it on entry.
- Implication: a `PipeParallel` as a `PipeBatch` branch drops the requested code, so the batch item's graph identity doesn't match the parallel's combined stuff. Now that the parallel always stamps, Phase 2 should honor `final_stuff_code` on the combined stuff (pass `code=` through `combine_stuffs` → `make_stuff`). A `TODO(Phase 2)` marks the spot in `_live_run_controller_pipe`.

**New/updated tests:** `tests/unit/pipelex/core/stuffs/test_composite_content.py` (round-trips incl. transport dump→hydrate), `tests/unit/pipelex/pipe_controllers/parallel/` (blueprint accept/reject + data.py), `tests/integration/.../pipe_parallel/test_pipe_parallel_always_combines.py` (+ fixture `parallel_always_combine.mthds`; stale-stamp regression + terminal-parallel main stuff; dry parity via `pipe_run_mode` parametrization), `tests/integration/.../pipe_parallel/test_pipe_parallel_output_validation.py` (library-level accept/reject via `acquire_library`). e2e graph expectations updated: the add_each-only graph now expects `parallel_combine: 2` edges.

### Checkpoint 2 — reached (Phase 2 complete)

**Code state:** Phase 2 fully implemented on `feature/Required-main-stuff`; commit `3c3cf4570` on top of `9acbd7a86`. `make agent-check` green; full `make agent-test` green (all tests passing). TDD followed: red tests written and confirmed failing before each behavioral change.

**What landed (invariant enforcement, per-surface):**

- **Graph tracer epilogue** (`pipe_abstract.py` `_run_pipe_traced` success path): `get_main_stuff()` direct read; `output_spec` built unconditionally; the `main_stuff is not None` gate on `output_concept_data` removed. The apologetic comment is gone.
- **Delivery executor** (`generate_result_files`): typed path reads `get_main_stuff()` (raises `WorkingMemoryStuffNotFoundError` when absent); raw path raises `PipeJobError` when the raw dump lacks a main stuff. The `try_local_hydrate_stuff` → raw-render fallback is unchanged (it's about local class availability, not missing main stuff). A missing main stuff surfaces as `StorageDeliveryError` at the `_store_results` boundary — the same handling path as any storage failure, so the caller's failure-webhook behavior is unchanged.
- **CLI run cores:** human core pretty-prints/saves/CSV-exports via `main_stuff` directly (the "--save-csv: no main stuff produced" exit branch is deleted); agent core builds `main_stuff_json` + `compact_result` unconditionally; agent API-runner core raises `PipeExecutionError` when a completed response has no main stuff under the announced key (the `main_stuff_name`-extension *name* fallback to `MAIN_STUFF_NAME` is kept — that's protocol-extension handling, not invariant softening).
- **OTel** (`make_output_json`): direct read; the `"{}"` fallback is gone (called on the success path only).
- **Wire models:** `PipelexPipeRunOutput.main_stuff_name: str` (required) and `PipelexRunResultExecute.main_stuff_name: str`. `resolve_main_stuff_root_key` returns `str` and raises `PipeJobError` on a memory with no main stuff; `PipelexRunResultExecute.from_pipe_output` now uses it (previously `aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME)` — which could announce a key that wasn't actually in `root`).
- **`PipeOutput.optional_main_stuff` DELETED** (breaking, in changelog). Workspace grep: only external consumer is `pipelex-demo-vibe` examples → Phase 3 sweep list.

**`final_stuff_code` resolution (design §7):** the parallel now honors it on the combined stuff. Implementation: `_run_branches_and_combine` captures `pipe_run_params.final_stuff_code` and clears it *before* branch fan-out (branches deep-copy the params, so they must not inherit the parent's requested code), then passes it as the new `code=` param on `StuffFactory.combine_stuffs` → `make_stuff`. Live/dry parity for free (shared helper). Pinned by `test_pipe_parallel_final_stuff_code.py` (combined stuff carries the code; branch outputs don't). **Noted, not addressed (pre-existing gaps, out of scope):** only `PipeLLM`/`PipeStructure` honor `final_stuff_code` among operators; `PipeBatch` still clears it on entry rather than stamping its aggregate list with it.

**Call-site audit (final state):** `grep get_optional_main_stuff` across `pipelex/` + `tests/` → the definition in `working_memory.py` (kept: pre-run/empty memory legitimately has none; public API for SDK-side pre-run checks) plus ONE justified in-source caller added by the review triage: `PipeCondition`'s pre-delivery checks (a mid-run "is there something to pass through / did anything get delivered" probe — legitimately optional at that point, converted into a loud `PipeRunError` when absent). Every post-run boundary call site was tightened.

**Review triage (Checkpoint 2):** The context-free review found and reproduced one real bug: the Phase 1 premise "every pipe stamps" was FALSE for `PipeCondition`'s `continue` outcome (live path returned the memory untouched) and for the dry run of an all-special-outcomes condition — so the tightened tracer epilogue (which fires on EVERY pipe node) crashed with a raw `WorkingMemoryStuffNotFoundError` on any continue-with-no-prior-main-stuff under tracing. Resolution (design-consistent, not a defensive revert): `continue` IS pass-through delivery — the delivered main stuff is the one already in memory; with nothing to pass through the pipe now raises a clear actionable `PipeRunError` at the semantic site ("map the outcome to a pipe, or place this condition after a producing step"), in both live and dry paths. Pinned by `tests/integration/.../pipe_condition/test_pipe_condition_continue_delivery.py` (pass-through identity + both fail-loud cases; run params constructed directly so keyless forced-DRY coercion can't swap the exercised path). Suite gap noted by the reviewer (nothing drove continue-with-no-main-stuff under tracing) is now covered. The reviewer confirmed the parallel `final_stuff_code` capture/clear mirrors `PipeBatch`'s existing pattern, and `combine_stuffs(code=)` has no empty-string/double-stamp edge. Related known-shaky area: `test_pipe_condition_continue_output_type.py` stays xfail (separate pre-existing bug, batch-over-continue aggregation semantics — untouched by this fix since batch branches always have a main stuff stamped).

**Test changes:** new `tests/integration/.../pipe_parallel/test_pipe_parallel_final_stuff_code.py`; `test_output_serialization.py` extended (aliased/direct root-key resolution + missing-main-stuff raises); `test_input_models.py` pins `main_stuff_name` required; `test_delivery_executor.py` mocks now carry a real main stuff + two new missing-main-stuff raise tests + `main_stuff.*` files asserted stored; `test_run_core_execution.py` obsolete `test_save_csv_no_main_stuff_exits` deleted; `test_run_pipe_tracer_metadata.py` + `test_run_cost_report.py` mock outputs made invariant-compliant; `test_mock_usage_direct.py` tightened.

**Cross-repo consequences flagged for Phase 3:** `main_stuff_name` is now required on the `/execute` response extension and `PipelexPipeRunOutput` — the closed `pipelex-transport` library and any consumer parsing these payloads must be checked; `pipelex-demo-vibe` uses the deleted `optional_main_stuff`.

### Checkpoint 3 — not reached
