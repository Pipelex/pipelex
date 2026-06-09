# Master plan — two dry-run modes on one foundation

> **What this is:** the overview tying together the two dry-run modes we want, how each is achieved, what they share, and who builds what. Neither per-mode tracker owns the *relationship* — this doc does. The per-mode plans:
>
> - **Mode 1 (in-memory activity)** → design [`followup-temporal-validation-activity.md`](./followup-temporal-validation-activity.md) · executable plan [`../../TODOS.md`](../../TODOS.md) · branch `feature/Dry-run-as-temporal-activity` (active).
> - **Mode 2 (full distribution, leaves mocked)** → [`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md) (own branch, not started).
> - **Design source:** [`D-plan.md`](./D-plan.md) §3.5 (run-mode ⟂ backend) + §4.8 (leaf-level mock) + §4.9 (validation activity).

## The two modes, in one sentence each

1. **In-memory activity (req 2).** The whole dry-run + validation runs **in-process inside a single Temporal activity** on a worker — nothing nested is dispatched — tracing the graph **in memory**. Purpose: let the hosted API offload "validate this bundle + give me its graph" to a worker, cheaply, with no DynamoDB round-trip and no AI calls.

2. **Full distribution, leaves mocked (req 1).** A dry-run goes through the **real** Temporal path — `TemporalPipeRun` → `WfPipeRouter` → child workflows → `act_llm_gen_*` / extract / img-gen activities — and the **leaf inside each dispatched activity** mocks instead of calling the model. Purpose: exercise the distribution machinery (dispatch, scheduling, serialization, routing, cross-worker propagation, graph assembly) without AI cost or latency.

## Why they don't conflict — one foundation, two backends

Both are the **same `run_mode=DRY`** run; they differ only in **backend** (where the leaf executes), which is the D-plan §3.5 thesis: *run mode is orthogonal to execution backend*. The foundation that makes both clean is the **leaf-level mock** (Part B / D-plan §4.8): mock at the cogt leaf keyed on `run_mode`; the content generator is run-mode-agnostic and only decides *where* the leaf runs.

| | Controllers (nested sub-pipes) | Cogt leaf (LLM/extract/img-gen) | Graph tracing | Result |
|---|---|---|---|---|
| **Mode 1 — in-memory activity** | forced **in-process** via `scoped_pipe_router` | forced **inline** via `scoped_content_generator` → mocks in-process | `scoped_event_log(InMemoryEventLog())` → in memory | one activity, zero nested dispatch, zero external I/O |
| **Mode 2 — full distribution** | hub default = **Temporal router** → child workflows | hub default = **`ContentGeneratorInWorkflow`** → dispatches `act_llm_gen_*`, mocks **inside** the activity | hub default = `temporal_dynamodb` (cross-worker assembly) | real distributed path, no AI spend |

The **only divergence is which content generator / router the run uses** — and both are selected by **per-call ContextVar overrides** (coroutine-local, restore-on-exit), so concurrent runs of different modes on one worker never cross-contaminate. Mode 1 *sets* the overrides; Mode 2 *leaves the hub defaults*. They are additive, not exclusive.

**Proof they already coexist:** `is_mock_inference` (shipped on the registry branch, #967) is the LLM slice of Mode 2 — `run_mode` stays LIVE so operators dispatch `act_llm_gen_*` normally, but the leaf fakes the call (`JobMetadata.is_mock_inference` → the `llm_generate.py` leaf branch). It runs today, alongside the pipe-level DRY path, with no conflict.

## The shared seam — `scoped_content_generator` (build once)

The single place the two modes touch. Under a Temporal-enabled hub, `get_content_generator()` returns `ContentGeneratorInWorkflow` **globally** (boot-time selection, `pipelex.py:370-385` — not contextual). So:

- **Mode 2 wants that default** — the in-workflow generator *is* how it dispatches leaf activities.
- **Mode 1 must override it to inline** — otherwise, once Part B routes the DRY mock through `get_content_generator()` at the leaf, Mode 1's in-process activity would dispatch `act_llm_gen_*` and break.

So `scoped_content_generator` (a hub ContextVar + context manager, mirroring `scoped_pipe_router` in `hub.py`, with `get_content_generator()` preferring the override) is needed by Mode 1 and is the seam Part C originally specced. **Decision (2026-06-09): build it now, in Mode 1's branch**, so Mode 1 is correct regardless of when Part B lands and the seam exists once for both.

### The ContextVar scope family (`pipelex/hub.py`)

| Scope | Exists? | Used by | Forces |
|---|---|---|---|
| `scoped_current_library` | yes (`hub.py`) | both / general | which library is current |
| `scoped_pipe_router` | yes (`hub.py`, PR #976) | Mode 1 | nested controllers run in-process, not via the Temporal router |
| `scoped_content_generator` | **to build (Mode 1 branch)** | Mode 1 | the leaf uses the inline generator, not the in-workflow one |
| `scoped_event_log` | **to build (Mode 1 branch, Phase 1)** | Mode 1 | graph trace events share one in-memory log across emit + assemble |

## Build order — who builds what

**Mode 1 — branch `feature/Dry-run-as-temporal-activity` (active now).** Full phase plan + checkpoints in [`../../TODOS.md`](../../TODOS.md):

- Phase 1 — `scoped_event_log` + shared in-memory tracing (fixes the two-instance emit/assemble problem: `pipeline_run_setup.py` write vs `tracing_assembly.py` read each call `make_event_log` separately; an in-memory log needs one shared instance).
- Phase 2 — in-process graph dry-run safe under a Temporal hub, reusing the bridge DIRECT primitive (`runtime_bridge/bridge.py::_run_direct` / `run_pipe_via_bridge`); **builds `scoped_content_generator`** and wraps the run in it + `scoped_event_log`.
- Phase 3 — the `act_dry_validate` activity (sweep + best-effort in-memory graph dry-run) + a one-step wrapper workflow + worker registration (`temporal/tasks.py`) + isolation test + **`temporal-e2e-validate` Tier 2d** (3-process distributed proof).
- Phase 4 — API dispatch (cross-repo `pipelex-api` `/validate`).
- Phase G0 *(optional, deferred)* — `temporalio` bump → true standalone activity (a runtime optimization over the wrapper workflow). **All decisions resolved 2026-06-09; no human gate remains** (dispatch = wrapper workflow on current `temporalio`).

**Mode 2 — own branch, later** ([`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md)):

- B1 — generalize the leaf mock from `is_mock_inference` (LLM-only) to `run_mode=DRY` across all leaves (LLM, extract, img-gen, templating); shared `cogt/content_generation/dry_mock.py`.
- B2 — collapse each operator's `_dry_run_pipe` so DRY routes through the hub content generator (stop hardcoding `ContentGeneratorDry()`); settle `is_mock_inference`'s fate. **Consumes `scoped_content_generator`** (already built by Mode 1's branch).
- B3 — verify Temporal + DRY e2e via **`temporal-e2e-validate` Tier 17**: activities dispatched, leaves mock inside them, no real IO, no API keys (the req-1 gate).

**Net:** Mode 1 builds the two new scopes and lands the in-memory activity; Mode 2 builds the all-leaf mock and verifies the distributed-DRY path, reusing the content-generator scope. Neither blocks the other; the shared seam is built once.

## Acceptance — each mode gated by a specific distributed `temporal-e2e-validate` tier

Both modes must be proven in the real 3-process topology (server + split workers + submitter), not only in unit/integration. Each adds a tier to the repo's `temporal-e2e-validate` skill following the Tier 2c precedent (a `references/mode-2-tiers.md` scenario with GREEN/RED + worker-log strong-check, a Mode-1 pytest companion, a Step-7 master-table row).

- **Mode 1 (req 2) — Tier 2d.** A Temporal-dispatched `/validate` runs the whole sweep + graph dry-run inside **one in-process activity** (zero nested dispatch — strong worker-idle check), traces the graph **in memory** (no NDJSON/DDB), and returns `{status map, GraphSpec}` in one round-trip; best-effort graph → `None` on failure; direct mode unchanged (req 3). Spec in [`../../TODOS.md`](../../TODOS.md) § Distributed verification.
- **Mode 2 (req 1) — Tier 17.** A `--temporal --dry-run` run **dispatches** `act_llm_gen_*` (+ extract/img-gen) to the worker and **mocks inside** each activity — no real IO, no API keys, zero-token suppressed usage, cross-worker graph still assembles. Flips today's Tier 8 "dry-run never dispatches" note. Spec in [`followup-leaf-run-mode-mock.md`](./followup-leaf-run-mode-mock.md) § Distributed verification.
