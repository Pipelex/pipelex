# Follow-up — Distributed validation as a Temporal activity

> **Status: deferred — own branch, not yet started, HARD-GATED.** Implements **D-plan Part C / D5 / req 2**. Split out of [`consolidation-as-built.md`](./consolidation-as-built.md) on 2026-06-01 (eng-review D1).
>
> **Design rationale:** [`D-plan.md`](./D-plan.md) §4.9 (distributed validation activity). **Risks:** D-plan §8 (nested-dispatch from the sweep, `temporalio` bump regression surface).
>
> **Depends on:** the consolidation (`BundleValidator`, [`consolidation-as-built.md`](./consolidation-as-built.md)) **and** the leaf run-mode follow-up ([`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md)). **Branch off the same D-plan.**
>
> **Scope note (D2):** the consolidation already migrated `pipelex-api/build/runner.py` to call `BundleValidator` in-process. So Phase C2 here only adds the **Temporal-dispatch** half on the validate route — not the in-process consumer.

Production flow (req 2): the web app calls the Pipelex API to validate a bundle; the API dispatches the validation to a Temporal worker as a **single standalone activity**; the worker runs the whole sweep in-process and returns the per-pipe status map.

## Status at a glance

| Phase | Title | Status | Commit |
|---|---|---|---|
| | **⛔ HUMAN GATE — pre-flight** | | |
| C0 | Bump `temporalio` + verify standalone-activity support | ☐ not started | |
| | **⛔ CHECKPOINT (SDK bump, separately reviewable)** | | |
| C1 | `scoped_content_generator` + `act_validate_bundle` | ☐ | |
| C2 | API dispatch (cross-repo `pipelex-api`) | ☐ | |
| | **⛔ CHECKPOINT F — all reqs met** | | |

Status legend: ☐ not started · ◐ in progress · ☑ done.

## Pre-flight — needs human input (HARD GATE)

- [ ] **(before C0 — HARD GATE) `temporalio` standalone activities.** Which SDK version to bump to, and does our Temporal Cloud / server version support standalone-activity execution? Needs infra knowledge/credentials. If unsupported, fall back to the one-step wrapper-workflow dispatch (§4.9). **Agent cannot resolve alone — must ask.**

> ### ⛔ HUMAN GATE — before C0 — **STOP, get answers**
>
> Do not start C0 until the **`temporalio`** Pre-flight item is answered (target version + Temporal Cloud/server standalone-activity support). Ask the user. Record the decision (and fallback choice if standalone is unsupported) here before proceeding.

## Phase C0 — Bump `temporalio` + verify standalone-activity support

- [ ] Bump `temporalio` past `1.23.0` in `pyproject.toml` (+ `uv.lock` via uv) to the confirmed version; confirm server/Cloud support.
- [ ] Run the **full** Temporal e2e suite (the SDK underpins the whole worker/runtime). Treat as self-contained + separately reviewable.
- [ ] If blocked: implement the one-step wrapper-workflow fallback (§4.9) instead; note it in the Handoff.

> ### ⛔ CHECKPOINT (after C0) — **MANDATORY STOP**
>
> **Verify:** full Temporal e2e green on the new SDK · `make agent-test` green · commit (own PR/review for the bump). **Next entry point: Phase C1.**

## Phase C1 — `scoped_content_generator` + `act_validate_bundle` (§4.9)

- [ ] *Tests first:* assert zero activity/workflow dispatches during a sweep run under a Temporal-enabled hub; assert concurrent invocations don't cross-contaminate the override.
- [ ] Add `_content_generator_override: ContextVar` + `scoped_content_generator(...)` mirroring `_library_id` / `scoped_current_library` in `hub.py`; make `get_content_generator()` prefer the override.
- [ ] Wrap `BundleValidator`'s sweep in `with scoped_content_generator(inline_dry_generator):` (forces the inline leaf; never dispatches nested activities).
- [ ] Add `tprl_pipe/act_validate_bundle.py` (thin wrapper over `BundleValidator.validate`) with the `convert_pipelex_errors` boundary; serializable in (`mthds_contents`/dirs, `allow_signatures`, `--pipe` selection) and out (`{pipe_ref: DryRunOutput}` + signature-check error).
- [ ] Register the activity on the worker; integration-test it in isolation. `make agent-check` + `make agent-test` green.

## Phase C2 — API dispatch (cross-repo `pipelex-api`)

- [ ] In `../pipelex-api`: switch the **validate route** to dispatch `act_validate_bundle` (standalone) when Temporal enabled, else call `BundleValidator` in-process. *(The `build/runner.py` consumer is already migrated in the consolidation — D2.)*
- [ ] Test both backends against the API.

> ### ⛔ CHECKPOINT F — after Phase C2 — **ALL REQUIREMENTS MET**
>
> req 1 (distributed DRY testing, activity-level mocks) · req 2 (production validation as a standalone Temporal activity) · req 3 (direct in-process).
>
> **Verify:** `pipelex` `make agent-test` green · Temporal e2e green · `pipelex-api` tests green both backends · commit. **Handoff:** final state + any follow-ups (e.g. §7 API endpoint unification).
