# Follow-up — Leaf-level run-mode mock (DRY honors the backend)

> **Status: deferred — own branch, not yet started.** Implements **D-plan Part B / D4 / req 1**. Split out of [`consolidation-as-built.md`](./consolidation-as-built.md) on 2026-06-01 (eng-review D1) so the in-process consolidation ships alone.
>
> **Design rationale:** [`D-plan.md`](./D-plan.md) §3.5 (run mode ⟂ backend) and §4.8 (leaf-level mock). **Risks:** D-plan §8 (object-mock fidelity, req-1 fidelity regressions).
>
> **Depends on:** the consolidation ([`consolidation-as-built.md`](./consolidation-as-built.md)) is *not* a hard prerequisite (this is a separable cogt/operator refactor). **Branch off the same D-plan.**
>
> **Relationship to the in-memory activity follow-up (corrected 2026-06-09):** this follow-up (req 1) is **orthogonal** to [`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md) (req 2), **not** a prerequisite for it — see "Still relevant — a distinct dry-run mode" below.
>
> **⚠️ Coordinate with the registry branch's Phase 5 (`fix/For-API-update`, decided 2026-06-06).** That branch ships `--mock-inference` / `is_mock_inference` as an *interim* trigger, deliberately built **leaf-first so it lands B1's core ahead of time**: a shared `cogt/content_generation/dry_mock.py` + a per-leaf dry branch keyed on a per-run flag carried on `JobMetadata`. So when this follow-up runs, **B1 collapses to "re-key that helper from `is_mock_inference` → `run_mode`"** (carrier + helper already exist — verify before building from scratch), and **B2 settles the fate of `is_mock_inference`** (retire vs keep a thin reportable-mock — see B2). One distinction to preserve when re-keying: `--mock-inference` emits *non-zero* synthetic usage so a cost report renders; `--dry-run` stays zero-token and its report is *suppressed*. See the registry feature's [`../registry/deferred-followups.md`](../registry/deferred-followups.md) (`--mock-inference` coverage + the `is_mock_inference` fate decision).

Goal: move the LIVE/DRY decision **down to the cogt leaf** so DRY honors the configured backend — DRY-on-Temporal dispatches `act_llm_gen_*` and mocks **inside** the activity, retiring the "DRY → local in-process" shortcut. Separable cogt/operator refactor (§4.8). **Resolve the Pre-flight items before starting.**

## Still relevant — a distinct dry-run mode (do NOT drop this file)

This describes a **different** dry-run mode from the in-memory in-process activity ([`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md)). Both are wanted; they're orthogonal `run_mode × backend` combinations of one foundation (mock at the leaf; the backend decides where the leaf runs — D-plan §3.5):

- **This file (req 1) — full distribution, leaf-only mocks.** A DRY run goes through the **real** Temporal path (`WfPipeRouter` → child workflows → `act_llm_gen_*` activities) and the **leaf inside each activity** mocks instead of calling the model. Purpose: **test the distribution machinery** (dispatch, scheduling, serialization, routing, cross-worker propagation) without AI cost or latency.
- **The other file (req 2) — one in-process activity, in-memory tracing.** The whole dry-run + validation runs **in-process inside a single activity** (nothing nested is dispatched), tracing the graph in memory. Purpose: offload validate+graph to a worker cheaply.

**Already partly shipped:** `is_mock_inference` (the registry branch's interim trigger) **is** the LLM slice of this mode — `run_mode` stays LIVE so operators dispatch `act_llm_gen_*` normally, but the leaf fakes the call (`JobMetadata.is_mock_inference` → the `llm_generate.py` leaf branch). So req-1 behavior already coexists, today, alongside the pipe-level DRY path — concrete proof the two modes don't conflict. B1/B2 generalize it from LLM-only + `is_mock_inference` to all leaves + `run_mode=DRY`.

**Shared seam with the in-memory activity — `scoped_content_generator`.** B2 routes the DRY mock through `get_content_generator()` at the leaf. Under a Temporal-enabled hub that returns `ContentGeneratorInWorkflow` **globally** (boot-time, `pipelex.py:370-385`). So after Part B, the **in-process** activity (req 2) must **force the inline content generator** or its leaf would dispatch — i.e. Part B reintroduces the `scoped_content_generator` need over there. Whichever follow-up lands first builds the inline-content-generator scope; the other consumes it. Coordinate the two so the seam is built once.

## Status at a glance

| Phase | Title | Status | Commit |
|---|---|---|---|
| B1 | Thread `run_mode` to cogt leaf + leaf DRY branch | ☐ not started | |
| B2 | Collapse operator dry path | ☐ | |
| | **⛔ CHECKPOINT D** | | |
| B3 | Verify Temporal + DRY e2e (**req-1 gate**) | ☐ | |
| | **⛔ CHECKPOINT E — follow-up complete** | | |

Status legend: ☐ not started · ◐ in progress · ☑ done.

## Pre-flight — ALL DECIDED (2026-06-10, with the user)

- [x] **(DECIDED) `run_mode` carrier = a new `CogtRunParams` class.** `PipeRunParams.run_mode` stays the pipe-tier source of truth (it already exists, `pipe_run_params.py`). The last mile across the operator→cogt boundary and the Temporal wire is a **new cogt-tier params class `CogtRunParams`**, built from `PipeRunParams` at the seam (single writer, `prepare_pipe_job`) and carried as a field on each cogt assignment (`LLMAssignment`, `ObjectAssignment`, img-gen/extract/templating). Rationale: type-explicit on the execution contract (can't be missed when building an assignment), keeps `JobMetadata` pure tracing/reporting identity, and gives `is_mock_inference` a natural home to migrate into (one flag-transport style, not two). **Rejected:** the `JobMetadata` mirror (the doc's old default — drifts metadata toward a behavior-flag grab-bag) and threading `PipeRunParams` into cogt (layer violation — drags pipe-tier concepts like multiplicity/batch params into a deliberately pipe-agnostic layer). Consequence for B1: not a pure re-key — B1 introduces `CogtRunParams` on the assignment models + Temporal converters, then keys the leaf branch on `cogt_run_params.run_mode == DRY`; `is_mock_inference`'s migration into it is settled in B2 alongside its fate.
- [x] **(DECIDED) Object mock = single schema-based site + fidelity test.** Both direct and dispatched leaves build via `SchemaToModelFactory` from the JSON schema — one code path, identical mock on both backends (the backend-parity this follow-up exists to deliver); fidelity bugs surface in cheap local unit tests instead of only on a worker. Accepted cost: direct mode gives up the in-hand original class — exotic format constraints (`json_schema_extra` hints dropped on round-trip) must declare `examples`/`mock_format`; the mandated fidelity test on a representative `StructuredContent` pins this.
- [x] **(DECIDED) Synthetic dry LLM report = keep, into a throwaway per-sweep registry.** The leaf stays unconditional (no "am I validating?" flag threading into cogt); the validation sweep opens one throwaway `UsageRegistry` so events have a home and die with it. Zero-token suppression already guarantees no rendered report; the runner-emission e2e keeps its cheap observable signal.
- [x] **(DECIDED) `ContentGeneratorDry` = delete outright in B2.** One mock mechanism remains: `run_mode=DRY` at the leaf. The boot `not needs_inference` fallback (`pipelex.py:371`) is re-expressed as a forced-DRY flag consumed at `prepare_pipe_job` (B2 mandated this anyway); Mode-1's scopes (`validate_pipes`, `dry_run_pipe_in_process`) pass the inline `ContentGenerator` instead (their callers already run DRY); tests using it as a double switch to the run_mode-threaded equivalent.

## Phase B1 — Thread `run_mode` to the leaf + add the leaf DRY branch (§4.8)

> **B1's core LANDED on the registry branch's Phase 5 (`fix/For-API-update`).** Already built: `JobMetadata.is_mock_inference`, the shared `cogt/content_generation/dry_mock.py` (synthetic-job reporting parameterized zero-vs-non-zero, plus the leaf mocks + `build_mock_object`), and the per-leaf branch in `llm_generate.py` keyed on `is_mock_inference`. So B1 reduces to: (1) carry `run_mode` on `JobMetadata` alongside `is_mock_inference` (same single-writer, `prepare_pipe_job`), and (2) re-key the leaf branch from `is_mock_inference` → `run_mode==DRY`. **Don't rebuild the helper.** Two caveats to finish what Phase 5 deliberately scoped out: it covers the **LLM leaf only** — `img_gen_*` / `extract_gen_pages` / `templating_gen_text` leaf branches are still TODO here (Phase 5 deferred them because their output is stored above the leaf; see that branch's §7); and `ContentGeneratorDry` still owns its method bodies (only its *reporting* delegates to `dry_mock`), so B2's collapse is still real work.

> **Interim hard guard already landed (F1, registry branch).** `img_gen_single_image` / `img_gen_image_list` / `extract_gen_pages`, plus `PipeSearch._live_run_operator_pipe` (web search has no `content_generation` leaf — it spends in the operator's live path), now **raise `MockInferenceUnsupportedError`** under `is_mock_inference` instead of silently calling the real provider. So when B1 adds the real synthetic-output leaf branch for img-gen/extract here, it is **replacing a fail-loud guard, not patching a silent-spend path** — delete the guard at that leaf as you add the DRY branch. Search has no leaf to thread `run_mode` into; decide whether it gains a real mock or keeps the guard when B1/B2 settle the operator dry paths. See `wip/registry/deferred-followups.md` (`--mock-inference` coverage).

- [ ] Confirm the funnel by grep: `ContentGenerator.make_llm_text` and `ContentGeneratorInWorkflow.make_llm_text` both build `LLMAssignment` and converge on `llm_gen_text(assignment)` (inline vs via `act_llm_gen_text`).
- [ ] Carry `run_mode` on `JobMetadata` (or the confirmed carrier); single-writer from `prepare_pipe_job` / `PipeRunParams`.
- [ ] *Tests first:* per-leaf DRY-branch unit tests; the object-mock-from-schema fidelity test on a representative `StructuredContent`.
- [ ] Add the DRY branch to each leaf — `llm_gen_text` (the `"DRY RUN: …"` string + `_report_dry_llm_job`), `llm_gen_object` / `llm_gen_object_list` (`DryRunFactory` build from `ObjectAssignment.object_class_schema` + report), `img_gen_*` (fake `ImageContent`), `extract_gen_pages` (mock pages), `templating_gen_text` (**preserve `check_jinja2_parsing`** then mock). Lift bodies from `ContentGeneratorDry` (consider a shared `cogt/content_generation/dry_mock.py`).
- [ ] Operators still call `ContentGeneratorDry` for now — **no behavior change yet**. `make agent-check` + `make agent-test` green.

## Phase B2 — Collapse the operator dry path (§4.8)

- [ ] Remove the pipe-level `ContentGeneratorDry()` swap from each operator's `_dry_run_operator_pipe` (`PipeLLM`, `PipeCompose`, `PipeImgGen`, `PipeExtract`, `PipeStructure` — grep for `ContentGeneratorDry()`). Route DRY through the hub content generator with `run_mode` threaded.
- [ ] Re-express the boot `not needs_inference` fallback (`pipelex.py:368`) as force-`run_mode=DRY`; apply the confirmed `ContentGeneratorDry` disposition.
- [ ] **Settle `is_mock_inference` / `--mock-inference`** (the registry branch's interim trigger). Now that `run_mode=DRY` honors the backend, **either** (a) *fully retire* the flag, its `JobMetadata` field, its CLI option, and the leaf branch's `is_mock_inference` arm — `run_mode=DRY` becomes the sole trigger — and re-key the registry branch's `temporal-e2e-validate` Tier 8b to assert on assembled `tokens_usages` (plain DRY emits zero-token usage, which Phase 3 *suppresses*, so the rendered table can't be asserted under DRY); **or** (b) *keep a thin reportable-mock* (the non-zero-synthetic-usage arm) precisely so Tier 8b can still validate the rendered cost report cheaply. Pick based on whether cheap rendered-report validation is worth one surviving flag. (Cross-ref: registry feature's [`../registry/deferred-followups.md`](../registry/deferred-followups.md).)
- [ ] `PipeSignature._dry_run_pipe` and controller dry behavior unchanged (no leaf op).
- [ ] Verify **direct + DRY** outcomes unchanged: full `make agent-test` green + spot-check a dry `validate --all` and a dry single-pipe run.

> ### ⛔ CHECKPOINT D — after Phase B2 — **MANDATORY STOP**
>
> Direct DRY re-expressed through the leaf with identical outcomes; Temporal cell not yet verified.
>
> **Verify:** `make agent-check` clean · `make agent-test` green · commit.
>
> **Handoff (fill in):** record final assignment/`run_mode` carrier shape, `ContentGeneratorDry` disposition, object-mock decision. **Next entry point: Phase B3 — Temporal+DRY e2e** (needs a Temporal server).

## Phase B3 — Verify Temporal + DRY end-to-end (**req-1 acceptance gate**)

The acceptance gate is a **specific distributed scenario** in the repo's `temporal-e2e-validate` skill — **Tier 17** — built to the Tier 2c/2d precedent (a 3-process scenario in `references/mode-2-tiers.md`, a Mode-1 pytest, a Step-7 master-table row). Full spec below.

- [ ] **Add `temporal-e2e-validate` Tier 17 — "DRY honors the Temporal backend (leaf mock inside the activity)".** Mode-2 3-process GREEN + RED + Mode-1 pytest + master-table row. See [§ Distributed verification](#distributed-verification--temporal-e2e-validate-mode-2--tier-17).
- [ ] `make agent-check` + `make agent-test` green; Temporal e2e green (Tier 17 GREEN and RED-proven).

## Distributed verification — `temporal-e2e-validate` (Mode 2 / Tier 17)

This tier **flips the current Tier 8 note** ("dry-run instantiates `ContentGeneratorDry` on the router and never dispatches `act_llm_gen_text`"): after Part B, DRY honors the backend and DOES dispatch, mocking inside the activity. That behavior change is the req-1 deliverable, so its proof is a new tier.

**Tier 17 — DRY honors the Temporal backend (leaf mock inside the activity).** New sequential tier (Step 3 family).

**Mode 2 (3-process) GREEN** — split workers up (`mode-2-setup.md`), Temporal-enabled; run a multi-step LLM bundle DRY:

```
pipelex run bundle .../library_crate/native_text_sequence.mthds --pipe native_text_sequence --temporal --dry-run --mock-inputs --no-logo --graph
```

- exit 0; **the worker DID dispatch `act_llm_gen_text`** (grep the runner session / `WorkflowHandle.fetch_history()` shows `ActivityTaskScheduled` for it) — the runner actually ran the activity. *(Pre-Part-B this dispatches nothing — that's the behavior we're changing.)*
- **The leaf mocked inside the activity:** no real provider call, **runs with NO API keys** (the "dry works with no inference configured" invariant must hold even though the activity dispatches), zero real spend, output is the DRY mock (`"DRY RUN: …"` / minted object), and usage is **zero-token / report suppressed** — distinct from `--mock-inference`, which keeps non-zero synthetic usage for a rendered cost report.
- cross-worker graph tracing assembled (`reactflow.html`); LibraryCrate propagation + serialization behaved as LIVE.
- **Extend to non-LLM leaves once B1 adds them:** rerun against extract (`pdf_extract_page_views`) and img-gen (`generate_image`) and assert `act_extract_gen_extract_pages` / `act_img_gen_images` are dispatched and mocked inside — this **replaces** the current `MockInferenceUnsupportedError` fail-loud guard at those leaves.

**Mode 2 RED (prove it bites):** revert B1's leaf re-key (DRY not threaded to the leaf) → DRY mocks on the router and dispatches nothing (the OLD behavior — fails the "dispatched" assertion); **or** force a real call (needs keys / spends). Confirm the **dispatched + mocked-inside + no-spend + no-keys** quartet flips. Restore.

**Mode 1 (pytest) companion** — `tests/integration/pipelex/temporal/test_dry_run_dispatches_and_mocks.py` (the DRY analogue of the existing `test_mock_inference_temporal.py`): assert `run_mode=DRY` over the in-process server dispatches `act_llm_gen_*` and the leaf mints the DRY mock with **zero-token, suppressed** usage, no real inference.

**Coordination with Tier 8b.** The existing `--mock-inference` cost arms (Tier 8b) are the LLM **cost-rendering** slice of this same mode (LIVE run mode + leaf mock, non-zero usage). B2's `is_mock_inference` fate decision (retire vs keep a thin reportable-mock) determines whether Tier 8b is **re-keyed** onto `run_mode=DRY` or kept as-is — settle it there, and update Tier 8b's scope manifest accordingly.

**Step-7 master-table row to add:** `Tier 17: DRY honors the backend | a --temporal --dry-run run dispatches act_llm_gen_* (+ extract/img-gen) to the worker and mocks INSIDE the activity — no real IO, no API keys needed, zero-token suppressed usage, cross-worker graph still assembles | PASS/FAIL | path | — `.

> ### ⛔ CHECKPOINT E — after Phase B3 — **Follow-up complete** — **MANDATORY STOP**
>
> Run mode is now orthogonal to backend across all four cells. **Req 1 satisfied.** Foundation for the Temporal-validation follow-up is in place.
>
> **Verify:** `temporal-e2e-validate` **Tier 17 GREEN and RED-proven** · full `make agent-test` green · commit.
>
> **Handoff (fill in):** (template) — **Next:** [`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md) (HARD GATE — get the `temporalio` answer first).
