# Dry-Run Refactor — Implementation Tracker

Execution spine for the dry-run / validation consolidation on branch `feature/Validate-with-signatures-4-fix-dry-run`. This file tracks **what to do and what's done**. The **design rationale** lives in [`wip/dry-run-refactor-draft/D-plan.md`](wip/dry-run-refactor-draft/D-plan.md) — referenced below as **§X**. When this tracker and D-plan disagree, D-plan is the source of truth for *intent*; update this tracker to match reality.

## How to use this doc

- Work **top to bottom**. Tick `- [ ]` → `- [x]` as each item lands. Keep the **Status at a glance** table in sync.
- **⛔ CHECKPOINT = mandatory hard stop.** Do **not** cross a ⛔ in the same session. At each one: run the verification block, fill the **Handoff** block in place, commit, then end the session. The next session cold-starts from there.
- **Line numbers in D-plan are indicative** (pinned to the branch state when written). **Verify by symbol** (grep for the function/class), never trust a line number. Do not edit by line number.
- **TDD (red → green → refactor).** Each phase lists *Tests first*, then *Implement*. Write the failing test, make it pass, then tidy. (Project preference.)
- **Verification commands** (from `CLAUDE.md` — never `make test`):
    - `make agent-check` — lint + types (ruff, pyright, mypy, plxt). Must be clean.
    - `make agent-test` — full suite, silent on success. Must be green at every ⛔.
    - Temporal arms (Parts B3 / C) need a server: see the `temporal-e2e-validate` skill and `CLAUDE.md` › "Temporal Integration Test Options".
- **No backward-compat** (project rule): change things outright; note breaking changes; don't add shims except the one explicitly allowed in §7 (Part A↔C ordering).

## Cold-start protocol (a fresh session starts here)

1. Read this section + **Status at a glance** + the **Handoff** block of the last completed ⛔ checkpoint.
2. Skim [`D-plan.md`](wip/dry-run-refactor-draft/D-plan.md) §1–§4 for the model (two operations; run-mode ⟂ backend) and the decisions D1–D5.
3. Resolve any **Pre-flight** item the upcoming phase depends on (ask the user if it's human-gated).
4. Resume at the **"Next entry point"** named in that Handoff block. Re-verify referenced symbols still exist before editing.

## Handoff block template (fill at every ⛔)

> **Completed:** which boxes/phases landed this session.
> **Decisions locked:** any Pre-flight / in-phase decision resolved, + the choice.
> **Final names/signatures:** the concrete signatures or names D-plan asked to record (e.g. `acquire_library(...)`, `prepare_pipe_job(...)`, the `run_mode` carrier).
> **Files touched (new/changed/deleted):** paths.
> **Deviations from plan + why.**
> **Surprises / new risks** discovered.
> **Test state:** last green commit SHA; anything skipped/xfail and why.
> **Next entry point:** exact phase + first action for the next session.

---

## Status at a glance

| Part | Phase | Title | Status | Commit |
|---|---|---|---|---|
| A | 0 | Unblock the leaf (relocate helpers) | ☐ not started | |
| A | 1 | Extract `acquire_library` / `prepare_pipe_job` seams | ☐ | |
| | | **⛔ CHECKPOINT A** | | |
| A | 2 | Build `BundleValidator` | ☐ | |
| A | 3 | Migrate callers + tests + config | ☐ | |
| | | **⛔ CHECKPOINT B** | | |
| A | 4 | Delete dead code | ☐ | |
| | | **⛔ CHECKPOINT C — Part A done (shippable)** | | |
| B | B1 | Thread `run_mode` to cogt leaf + leaf DRY branch | ☐ | |
| B | B2 | Collapse operator dry path | ☐ | |
| | | **⛔ CHECKPOINT D** | | |
| B | B3 | Verify Temporal + DRY e2e (**req-1 gate**) | ☐ | |
| | | **⛔ CHECKPOINT E — Part B done** | | |
| | | **⛔ HUMAN GATE — Part C pre-flight** | | |
| C | C0 | Bump `temporalio` + verify standalone-activity support | ☐ | |
| | | **⛔ CHECKPOINT (SDK bump, separately reviewable)** | | |
| C | C1 | `scoped_content_generator` + `act_validate_bundle` | ☐ | |
| C | C2 | API dispatch (cross-repo `pipelex-api`) | ☐ | |
| | | **⛔ CHECKPOINT F — all reqs met** | | |

Status legend: ☐ not started · ◐ in progress · ☑ done.

---

## Pre-flight — needs human input

Resolve **before** the phase that depends on it. These are *your* calls (or need infra access), not the agent's to guess. Record the answer in the relevant checkpoint Handoff.

- [ ] **(before B1) `run_mode` carrier.** Confirm: carry `run_mode` on `JobMetadata` (recommended, lowest-churn — §4.8) vs an explicit field on each cogt assignment. Default if unanswered: `JobMetadata`.
- [ ] **(before B1) object-mock-from-schema fidelity.** Single schema-based mock site (default) vs two-site (class-based direct + schema-based activity). §4.8 / §8. Default if unanswered: single site + fidelity test.
- [ ] **(before B1/B2) synthetic dry LLM report.** Keep `_report_dry_llm_job` firing during the validation sweep, or gate it off so validation is report-silent (runner-emission e2e keeps it on)? §8. Default if unanswered: open one throwaway per-sweep registry, keep the report.
- [ ] **(before B2) `ContentGeneratorDry` disposition.** Delete outright, or keep as a thin force-`run_mode=DRY` facade for the boot `not needs_inference` fallback? §4.8.
- [ ] **(before C0 — HARD GATE) `temporalio` standalone activities.** Which SDK version to bump to, and does our Temporal Cloud / server version support standalone-activity execution? Needs infra knowledge/credentials. If unsupported, fall back to the one-step wrapper-workflow dispatch (§4.9). **Agent cannot resolve alone — must ask.**

---

## Part A — In-process validation consolidation (D1–D3, req 3)

Goal: one `BundleValidator` service over a shared `acquire_library` / `prepare_pipe_job` seam; delete the parallel dry-run modules. Mock still minted at the pipe level here (Part B moves it). Ordered to keep every intermediate state green given `dry_run.py` is imported by `pipe_signature.py`.

### Phase 0 — Unblock the leaf (§4.7)

- [ ] Confirm importers of the two helpers by grep: `convert_to_working_memory_format`, `convert_stuff_spec_to_typed_named`.
- [ ] Relocate both into `WorkingMemoryFactory` (`pipelex/core/memory/working_memory_factory.py`) — confirmed present — or a `mock_inputs.py` beside it.
- [ ] Rewire `pipe_signature/pipe_signature.py` and `pipeline/pipeline_run_setup.py` imports.
- [ ] `make agent-check` clean; `make agent-test` green. No behavior change expected.

### Phase 1 — Extract the execution seams (§4.1 / D2)

- [ ] *Tests first:* a focused test that `prepare_pipe_job(...)` builds an equivalent `PipeJob` against a pre-opened library (vs today's `pipeline_run_setup`).
- [ ] Extract `acquire_library(...)` from `pipeline_run_setup` (set-current / open / load dirs+blueprints+bundle; owns load-failure teardown).
- [ ] Extract `prepare_pipe_job(library_id, pipe_code, *, execution_config, pipe_run_mode, inputs, graph_context, otel_context, pipeline_run_id, output_name, ...)` — pure `PipeJob` builder (no registration / telemetry / library mutation).
- [ ] Recompose `pipeline_run_setup` as the thin self-contained wrapper over the seams (`add_new_pipeline` → `acquire_library` → tracer → `prepare_pipe_job` → registry/otel/`PIPELINE_EXECUTE` → return). Runner public API untouched.
- [ ] Verify LIVE + self-contained DRY paths unchanged (existing runner/pipeline tests green).
- [ ] `make agent-check` + `make agent-test` green.

> ### ⛔ CHECKPOINT A — after Phase 1 — **MANDATORY STOP**
>
> Seams exist; self-contained path recomposed with no behavior change; signature runtime no longer depends on `dry_run.py`. Nothing consumes the seams for batch use yet — clean boundary.
>
> **Verify:** `make agent-check` clean · `make agent-test` green · commit.
>
> **Handoff (fill in):**
> - Completed:
> - Decisions locked:
> - Final names/signatures: `acquire_library(...)` = … ; `prepare_pipe_job(...)` = … ; any `pipeline_run_setup` shape change =
> - Files touched:
> - Deviations + why:
> - Surprises / new risks:
> - Test state (green SHA):
> - Next entry point: **Phase 2 — Build `BundleValidator`**.

### Phase 2 — Build `BundleValidator` (§4.2, D1/D3/D5)

- [ ] *Tests first:* port `tests/unit/pipelex/pipe_run/test_dry_run.py` coverage onto the service surface; add a cross-package partial-validation test (the `PipeNotFoundError → SKIPPED` recursive `__cause__` walk).
- [ ] Implement `pipelex/pipeline/bundle_validator.py` composing the seams against a **direct** primitive (a locally-constructed `PipeRun`, **not** `get_pipe_run()` — §4.1/D5): acquire-once → signature pre-pass → `validate_with_libraries` pass → per-pipe `prepare_pipe_job` + `direct_pipe_run.run` → `SUCCESS/FAILURE/SKIPPED` classify → single `PIPE_DRY_RUN` event → `try/finally` teardown.
- [ ] `SKIPPED` reclassification = recursive `_root_cause_is(exc, PipeNotFoundError)` walk (§4.2 step 5 / §8).
- [ ] Relocate `DryRunStatus` / `DryRunOutput` into the `bundle_validator` module.
- [ ] Verify the report-delegate need (§8 — DRY emits a synthetic report): open **one** report registry per sweep (single open/clear), never per pipe. Assert exactly one `PIPE_DRY_RUN`, no stray `PIPELINE_EXECUTE`/`PIPELINE_COMPLETE`.
- [ ] Built behind no callers yet, against the still-present `dry_run.py`. `make agent-check` + `make agent-test` green.
- [ ] *(soft stop)* If context > ~60%, treat end of Phase 2 as a stop: fill a Handoff note and resume at Phase 3 next session.

### Phase 3 — Migrate the callers (§ Part A / D3)

- [ ] Point at `BundleValidator`: `validate_bundle` / `validate_bundles_from_directory`, both `cli/.../validate/_validate_core.py`, `builder/operations/validate_ops.py`, `builder/operations/runner_code_ops.py`.
- [ ] Rewire tests importing soon-to-be-deleted symbols (`dry_run_pipe`/`dry_run_pipes`/`DryRunStatus`/`convert_to_working_memory_format`): the `pipe_signature` integration tests, the `pipe_sequence` dry-run tests, the signature-validation e2e (grep to confirm the current set — don't trust a stale list).
- [ ] Migrate `pipelex.toml` `allowed_to_fail_pipes` to namespaced refs: `infinite_loop_1` → `failing_pipelines.infinite_loop_1`; **delete the obsolete `pipe_builder` entry**.
- [ ] Verify single-pipe `validate <pipe>` / `--pipe` slice + friendly `SignaturesNotAllowedError` rendering still fire.
- [ ] `make agent-check` + `make agent-test` green.

> ### ⛔ CHECKPOINT B — after Phase 3 — **MANDATORY STOP**
>
> All validation traffic now goes `BundleValidator` → shared seam; `dry_run.py` execution functions unreferenced *inside this repo* (external `pipelex-api` handled in Part C / §7).
>
> **Verify:** signature e2e + `pipe_signature` integration suites green · full `make agent-test` green · commit.
>
> **Handoff (fill in):** (use template) — **Next entry point: Phase 4 — Delete dead code.**

### Phase 4 — Delete dead code (§5)

- [ ] Delete `pipe_run/dry_pipe_router.py`, `pipe_run/dry_run_with_graph.py`, and the now-unreferenced `pipe_run/dry_run.py` (grep to confirm zero in-repo importers first).
- [ ] Settle `dry_run_pipeline.py` (keep thin, or inline into `graph/graph_rendering.py`).
- [ ] `make cleanderived` if collection gets confused; `make agent-check` + `make agent-test` green.

> ### ⛔ CHECKPOINT C — after Phase 4 — **Part A complete (shippable)** — **MANDATORY STOP**
>
> The branch's original goal is met. DRY still mocks at the pipe level (pre-D4) — fine; Part B changes *where* the mock is minted, not validation outcomes. Natural point to ship Part A alone (mind the §7 Part A↔C ordering note re: `pipelex-api`).
>
> **Verify:** full `make agent-test` green · `make agent-check` clean · commit (consider opening the PR for Part A here).
>
> **Handoff (fill in):** (use template) — **Next entry point: Part B / Phase B1** (resolve B1 Pre-flight items first).

---

## Part B — Run-mode/backend orthogonality at the cogt leaf (D4, req 1)

Goal: move the LIVE/DRY decision **down to the cogt leaf** so DRY honors the backend (DRY-on-Temporal dispatches `act_llm_gen_*` and mocks *inside* the activity). Separable cogt/operator refactor (§4.8). **Resolve the B1 Pre-flight items before starting.**

### Phase B1 — Thread `run_mode` to the leaf + add the leaf DRY branch (§4.8)

- [ ] Confirm the funnel by grep: `ContentGenerator.make_llm_text` and `ContentGeneratorInWorkflow.make_llm_text` both build `LLMAssignment` and converge on `llm_gen_text(assignment)` (inline vs via `act_llm_gen_text`).
- [ ] Carry `run_mode` on `JobMetadata` (or the confirmed carrier); single-writer from `prepare_pipe_job` / `PipeRunParams`.
- [ ] *Tests first:* per-leaf DRY-branch unit tests; the object-mock-from-schema fidelity test on a representative `StructuredContent`.
- [ ] Add the DRY branch to each leaf — `llm_gen_text` (the `"DRY RUN: …"` string + `_report_dry_llm_job`), `llm_gen_object` / `llm_gen_object_list` (`DryRunFactory` build from `ObjectAssignment.object_class_schema` + report), `img_gen_*` (fake `ImageContent`), `extract_gen_pages` (mock pages), `templating_gen_text` (**preserve `check_jinja2_parsing`** then mock). Lift bodies from `ContentGeneratorDry` (consider a shared `cogt/content_generation/dry_mock.py`).
- [ ] Operators still call `ContentGeneratorDry` for now — **no behavior change yet**. `make agent-check` + `make agent-test` green.

### Phase B2 — Collapse the operator dry path (§4.8)

- [ ] Remove the pipe-level `ContentGeneratorDry()` swap from each operator's `_dry_run_pipe` (`PipeLLM`, `PipeImgGen`, `PipeExtract`/`PipeOcr`, templating operators — grep for `ContentGeneratorDry()` and `_dry_run_pipe`). Route DRY through the hub content generator with `run_mode` threaded.
- [ ] Re-express the boot `not needs_inference` fallback as force-`run_mode=DRY`; apply the confirmed `ContentGeneratorDry` disposition.
- [ ] `PipeSignature._dry_run_pipe` and controller dry behavior unchanged (no leaf op).
- [ ] Verify **direct + DRY** outcomes unchanged: full `make agent-test` green + spot-check a dry `validate --all` and a dry single-pipe run.

> ### ⛔ CHECKPOINT D — after Phase B2 — **MANDATORY STOP**
>
> Direct DRY re-expressed through the leaf with identical outcomes; Temporal cell not yet verified.
>
> **Verify:** `make agent-check` clean · `make agent-test` green · commit.
>
> **Handoff (fill in):** record final assignment/`run_mode` carrier shape, `ContentGeneratorDry` disposition, object-mock decision. **Next entry point: Phase B3 — Temporal+DRY e2e** (needs a Temporal server).

### Phase B3 — Verify Temporal + DRY end-to-end (**req-1 acceptance gate**)

- [ ] With a Temporal server (`temporal-e2e-validate` topology), run a pipeline `run_mode=DRY` and assert: `act_llm_gen_*` + extract/img-gen activities **are dispatched** and **mock inside the activity**; LibraryCrate propagation, cross-process serialization, graph tracing behave as LIVE; **no real LLM/IO** occurs.
- [ ] Add a DRY arm to the Temporal e2e suite.
- [ ] `make agent-check` + `make agent-test` green; Temporal e2e green.

> ### ⛔ CHECKPOINT E — after Phase B3 — **Part B complete** — **MANDATORY STOP**
>
> Run mode is now orthogonal to backend across all four cells. **Req 1 satisfied.**
>
> **Verify:** Temporal+DRY e2e green · full `make agent-test` green · commit.
>
> **Handoff (fill in):** (template) — **Next entry point: ⛔ HUMAN GATE → Part C / Phase C0.**

---

## Part C — Distributed validation as a Temporal activity (D5, req 2)

Depends on Part A (`BundleValidator`) and Part B (inline leaf mock). Cross-repo (`pipelex-api`).

> ### ⛔ HUMAN GATE — before Part C — **STOP, get answers**
>
> Do not start C0 until the **`temporalio`** Pre-flight item is answered (target version + Temporal Cloud/server standalone-activity support). Ask the user. Record the decision (and fallback choice if standalone is unsupported) here before proceeding.

### Phase C0 — Bump `temporalio` + verify standalone-activity support

- [ ] Bump `temporalio` past `1.23.0` in `pyproject.toml` (+ `uv.lock` via uv) to the confirmed version; confirm server/Cloud support.
- [ ] Run the **full** Temporal e2e suite (the SDK underpins the whole worker/runtime). Treat as self-contained + separately reviewable.
- [ ] If blocked: implement the one-step wrapper-workflow fallback (§4.9) instead; note it in the Handoff.

> ### ⛔ CHECKPOINT (after C0) — **MANDATORY STOP**
>
> **Verify:** full Temporal e2e green on the new SDK · `make agent-test` green · commit (own PR/review for the bump). **Next entry point: Phase C1.**

### Phase C1 — `scoped_content_generator` + `act_validate_bundle` (§4.9)

- [ ] *Tests first:* assert zero activity/workflow dispatches during a sweep run under a Temporal-enabled hub; assert concurrent invocations don't cross-contaminate the override.
- [ ] Add `_content_generator_override: ContextVar` + `scoped_content_generator(...)` mirroring `_library_id` / `scoped_current_library` in `hub.py`; make `get_content_generator()` prefer the override.
- [ ] Wrap `BundleValidator`'s sweep in `with scoped_content_generator(inline_dry_generator):` (forces the inline leaf; never dispatches nested activities).
- [ ] Add `tprl_pipe/act_validate_bundle.py` (thin wrapper over `BundleValidator.validate`) with the `convert_pipelex_errors` boundary; serializable in (`mthds_contents`/dirs, `allow_signatures`, `--pipe` selection) and out (`{pipe_ref: DryRunOutput}` + signature-check error).
- [ ] Register the activity on the worker; integration-test it in isolation. `make agent-check` + `make agent-test` green.

### Phase C2 — API dispatch (cross-repo `pipelex-api`)

- [ ] In `../pipelex-api`: switch the validate route + `build/runner.py` to dispatch `act_validate_bundle` (standalone) when Temporal enabled, else call `BundleValidator` in-process. Removes the last `dry_run_pipes` consumer (supersedes the §7 deferral).
- [ ] Test both backends against the API.

> ### ⛔ CHECKPOINT F — after Phase C2 — **ALL REQUIREMENTS MET**
>
> req 1 (distributed DRY testing, activity-level mocks) · req 2 (production validation as a standalone Temporal activity) · req 3 (direct in-process).
>
> **Verify:** `pipelex` `make agent-test` green · Temporal e2e green · `pipelex-api` tests green both backends · commit. **Handoff:** final state + any follow-ups (e.g. §7 API endpoint unification).
