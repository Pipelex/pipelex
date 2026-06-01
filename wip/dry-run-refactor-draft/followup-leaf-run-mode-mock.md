# Follow-up — Leaf-level run-mode mock (DRY honors the backend)

> **Status: deferred — own branch, not yet started.** Implements **D-plan Part B / D4 / req 1**. Split out of [`/TODOS.md`](../../TODOS.md) on 2026-06-01 (eng-review D1) so the in-process consolidation ships alone.
>
> **Design rationale:** [`D-plan.md`](./D-plan.md) §3.5 (run mode ⟂ backend) and §4.8 (leaf-level mock). **Risks:** D-plan §8 (object-mock fidelity, req-1 fidelity regressions).
>
> **Depends on:** the consolidation ([`/TODOS.md`](../../TODOS.md)) is *not* a hard prerequisite (this is a separable cogt/operator refactor), but the Temporal-validation follow-up builds on **both**, so sequence this after the consolidation lands. **Branch off the same D-plan.**

Goal: move the LIVE/DRY decision **down to the cogt leaf** so DRY honors the configured backend — DRY-on-Temporal dispatches `act_llm_gen_*` and mocks **inside** the activity, retiring the "DRY → local in-process" shortcut. Separable cogt/operator refactor (§4.8). **Resolve the Pre-flight items before starting.**

## Status at a glance

| Phase | Title | Status | Commit |
|---|---|---|---|
| B1 | Thread `run_mode` to cogt leaf + leaf DRY branch | ☐ not started | |
| B2 | Collapse operator dry path | ☐ | |
| | **⛔ CHECKPOINT D** | | |
| B3 | Verify Temporal + DRY e2e (**req-1 gate**) | ☐ | |
| | **⛔ CHECKPOINT E — follow-up complete** | | |

Status legend: ☐ not started · ◐ in progress · ☑ done.

## Pre-flight — needs human input

Resolve **before** the phase that depends on it. Record the answer in the relevant checkpoint Handoff.

- [ ] **(before B1) `run_mode` carrier.** Confirm: carry `run_mode` on `JobMetadata` (recommended, lowest-churn — §4.8) vs an explicit field on each cogt assignment. Default if unanswered: `JobMetadata`.
- [ ] **(before B1) object-mock-from-schema fidelity.** Single schema-based mock site (default) vs two-site (class-based direct + schema-based activity). §4.8 / §8. Default if unanswered: single site + fidelity test.
- [ ] **(before B1/B2) synthetic dry LLM report.** Keep `_report_dry_llm_job` firing during the validation sweep, or gate it off so validation is report-silent (runner-emission e2e keeps it on)? §8. Default if unanswered: open one throwaway per-sweep registry, keep the report.
- [ ] **(before B2) `ContentGeneratorDry` disposition.** Delete outright, or keep as a thin force-`run_mode=DRY` facade for the boot `not needs_inference` fallback? §4.8.

## Phase B1 — Thread `run_mode` to the leaf + add the leaf DRY branch (§4.8)

- [ ] Confirm the funnel by grep: `ContentGenerator.make_llm_text` and `ContentGeneratorInWorkflow.make_llm_text` both build `LLMAssignment` and converge on `llm_gen_text(assignment)` (inline vs via `act_llm_gen_text`).
- [ ] Carry `run_mode` on `JobMetadata` (or the confirmed carrier); single-writer from `prepare_pipe_job` / `PipeRunParams`.
- [ ] *Tests first:* per-leaf DRY-branch unit tests; the object-mock-from-schema fidelity test on a representative `StructuredContent`.
- [ ] Add the DRY branch to each leaf — `llm_gen_text` (the `"DRY RUN: …"` string + `_report_dry_llm_job`), `llm_gen_object` / `llm_gen_object_list` (`DryRunFactory` build from `ObjectAssignment.object_class_schema` + report), `img_gen_*` (fake `ImageContent`), `extract_gen_pages` (mock pages), `templating_gen_text` (**preserve `check_jinja2_parsing`** then mock). Lift bodies from `ContentGeneratorDry` (consider a shared `cogt/content_generation/dry_mock.py`).
- [ ] Operators still call `ContentGeneratorDry` for now — **no behavior change yet**. `make agent-check` + `make agent-test` green.

## Phase B2 — Collapse the operator dry path (§4.8)

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

## Phase B3 — Verify Temporal + DRY end-to-end (**req-1 acceptance gate**)

- [ ] With a Temporal server (`temporal-e2e-validate` topology), run a pipeline `run_mode=DRY` and assert: `act_llm_gen_*` + extract/img-gen activities **are dispatched** and **mock inside the activity**; LibraryCrate propagation, cross-process serialization, graph tracing behave as LIVE; **no real LLM/IO** occurs.
- [ ] Add a DRY arm to the Temporal e2e suite.
- [ ] `make agent-check` + `make agent-test` green; Temporal e2e green.

> ### ⛔ CHECKPOINT E — after Phase B3 — **Follow-up complete** — **MANDATORY STOP**
>
> Run mode is now orthogonal to backend across all four cells. **Req 1 satisfied.** Foundation for the Temporal-validation follow-up is in place.
>
> **Verify:** Temporal+DRY e2e green · full `make agent-test` green · commit.
>
> **Handoff (fill in):** (template) — **Next:** [`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md) (HARD GATE — get the `temporalio` answer first).
