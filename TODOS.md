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

- [ ] Verify acceptance criteria + full gates.
- [ ] Commit Phase 1.
- [ ] Update this file (checkpoint log below) + design doc status for cold start.
- [ ] Fan out context-free Sonnet-5 `/code-review` sub-agent on the Phase 1 diff (pointer only).
- [ ] Triage findings: fix defects / defer tradeoffs to `wip/required-main-stuff/`.

## Phase 2 — Enforce the invariant across in-repo surfaces

Once every pipe stamps, "a completed run has a main stuff" is guaranteed; tighten the defensive branches from optional to direct.

- [ ] Graph tracer output-spec branch in `pipelex/core/pipes/pipe_abstract.py` — remove the defensive branch and its apologetic comment ("main_stuff may not exist for pipes like PipeParallel…").
- [ ] Delivery executor `pipelex/pipe_run/delivery_executor.py`: always write the `main_stuff.*` artifact files for completed runs (kills the "empty envelope" failure mode).
- [ ] CLI run cores: `pipelex/cli/commands/run/_run_core.py` + `pipelex/cli/agent_cli/commands/run/_run_core.py` — drop the "no main output produced" branches for live runs.
- [ ] OTel telemetry attribute extraction: `pipelex/system/telemetry/otel_factory.py`.
- [ ] Wire models go non-optional (`main_stuff_name: str`): `pipelex/runtime_bridge/payloads.py`, `pipelex/runtime_bridge/serialization.py` (`resolve_main_stuff_root_key`), `pipelex/pipeline/pipeline_response.py` (`PipelexRunResultExecute`), `pipelex/cli/agent_cli/commands/run/_run_core_api.py`. Temporal payload history is not a concern — never shipped to prod.
- [ ] Audit every remaining `get_optional_main_stuff` call site: `WorkingMemory.get_optional_main_stuff` itself **stays** (pre-run/empty memory legitimately has none); each post-run boundary call site is either tightened or justified in the checkpoint log.
- [ ] Resolve the **`final_stuff_code`** open question (design §7) using the Phase 1c findings: presumably honor it on the combined stuff like operators do.
- [ ] Gates: `make agent-check` + full `make agent-test` green.

### ⛔ CHECKPOINT 2 — MANDATORY STOP

Acceptance: no defensive main-stuff branch left for completed live runs; wire `main_stuff_name` non-optional; call-site audit documented; all gates green. Cross-repo work starts fresh from here — this checkpoint's TODOS update is the cold-start context for that session.

- [ ] Verify acceptance criteria + full gates.
- [ ] Commit Phase 2.
- [ ] Update this file (checkpoint log: final call-site audit results, `final_stuff_code` decision) + design doc status.
- [ ] Fan out context-free Sonnet-5 `/code-review` sub-agent on the Phase 2 diff (pointer only).
- [ ] Triage findings: fix defects / defer tradeoffs to `wip/required-main-stuff/`.

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

- [ ] `final_stuff_code`: investigate in Phase 1c, resolve in Phase 2.
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

### Checkpoint 2 — not reached

### Checkpoint 3 — not reached
