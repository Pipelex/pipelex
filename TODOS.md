# PR #969 — Framework-agnostic Pipelex runtime bridge (reviewer's guide)

What this PR does, how, and why it's the right shape. Base branch: `dev`.

The **code** core is small and concentrated. Concentrate review on:

- `pipelex/runtime_bridge/` — the new package (the point of the PR)
- `pipelex/temporal/tprl_pipe/act_*.py` — the thin-wrapper rewiring
- `pipelex/hub.py` — the `scoped_pipe_router` addition
- `tests/{unit,integration}/pipelex/runtime_bridge/`

**Not review material:**

- `wip/` — internal planning / triage notes, not part of the shipped surface. The bridge's own review-triage and deferred-items record lives in `wip/runtime-bridge/README.md`; the rest is unrelated track planning.
- `docs/distributed-execution/mistral-workflows/` — forward-looking user docs for the `MISTRAL_NATIVE` mode, whose host package (`pipelex-mistralai-workflows`) ships separately. The mode's bridge-side plumbing is in this PR; the host integration is not.

## What it does

Adds one host-runtime-agnostic surface — `pipelex/runtime_bridge/` — through which any embedding runtime (Mistral Workflows, a raw Temporal worker, a future plugin, or plain Python) invokes a Pipelex pipe from inside its own activity. Single entry point:

```python
from pipelex.runtime_bridge.bridge import run_pipe_via_bridge, PipelexPipeRunInput
output = await run_pipe_via_bridge(PipelexPipeRunInput(pipe_code=..., inputs={...}, execution_mode=...))
```

Input and output are JSON-safe pydantic models (`PipelexPipeRunInput` / `PipelexPipeRunOutput`, both `extra="forbid"`), so the boundary survives a serialization hop across a worker/activity without leaking Pipelex internals.

## Execution modes (`execution_mode.py`)

The caller chooses how the pipe runs via `PipelexExecutionMode` (a `StrEnum`; the JSON wire values are lowercase — `direct`, `temporal_blocking`, `temporal_fire_and_forget`, `mistral_native`):

- `DIRECT` — in-process, no Temporal; the activity blocks until the pipe completes. Fastest, simplest; works even inside a Temporal-enabled worker (forces local execution).
- `TEMPORAL_BLOCKING` — dispatch the pipe as a Pipelex Temporal workflow and await it. Needs `pipelex[temporal]`.
- `TEMPORAL_FIRE_AND_FORGET` — dispatch and return the `workflow_id` immediately; completion arrives out-of-band via `DeliveryAssignment` (webhook/storage). Needs `pipelex[temporal]` + a `delivery_assignment_dump`.
- `MISTRAL_NATIVE` — decompose the pipe into native Mistral Workflows primitives (controllers → child workflows, leaves → activities). Needs the `pipelex-mistralai-workflows` package.

Mode-specific dependencies are pulled in by **lazy import inside the matching branch only** — the bridge module imports nothing host-specific at top level. So DIRECT runs with neither extra installed, and a missing extra raises a precise, install-hint error (`MissingPipelexTemporalExtraError` / `MissingMistralWorkflowsPluginError`) rather than an `ImportError` at module load.

## How a call flows (`bridge.py::run_pipe_via_bridge`)

1. `ensure_pipelex_booted()` — idempotent, thread-safe boot; adopts an externally-created singleton if one already exists.
2. Decode `library_crate_dump` / `delivery_assignment_dump` and `_validate_input` — mode-specific guards (e.g. fire-and-forget must carry a delivery target, else completion would be silently dropped). A malformed dump becomes a `PipelexBridgeDispatchError`, not a raw `pydantic.ValidationError`.
3. `_scoped_library_for_crate` — if the caller passed a `library_crate_dump`, open a **per-call scoped library** with its own `ClassRegistry` (pre-seeded from the global one), load it from the crate, tear it down on exit. This is what lets a stateless / multi-tenant worker run a pipe whose definition travels in the request, without leaking dynamic concept classes into the global registry.
4. `build_pipe_job_from_input` — hydrate a `PipeJob` (working memory from inputs, job metadata, optional `trace_context`).
5. `match execution_mode:` — dispatch to that mode's runner.

## The primitives lift (`runtime_bridge/primitives/`)

The framework-agnostic bodies behind the Temporal activities (delivery, trace flush, hydration, pipe classification, submitter hydration) live in `runtime_bridge.primitives`. The `pipelex/temporal/tprl_pipe/act_*.py` files are **thin `@activity.defn` wrappers** that decode their arg and delegate to the shared primitive (see `act_deliver.py`). The Mistral-native path calls the same primitives. One copy of each primitive, two host runtimes.

Graph + usage assembly is deliberately **not** a bridge primitive: it lives in `pipe_run/tracing_assembly.py` (`assemble_tracing` reads the event stream once and produces both the `GraphSpec` and token usage), behind the thin `act_assemble_tracing` activity. That module is the framework-agnostic home for tracing assembly; the bridge consumes the same execution path as any local run and does not own it.

## Why this is the right shape (claims a reviewer can check)

- **Separation of concerns.** "How a host invokes a pipe" (bridge) is now distinct from "how Pipelex executes a pipe" (`pipe_run` / `pipe_controllers`) and from "Temporal SDK glue" (`pipelex.temporal`). *Verify:* `runtime_bridge/` has no `temporalio` / `mistralai` import at module top level — host SDKs appear only inside lazy-import branches (`grep -rn "import temporalio\|import mistralai" pipelex/runtime_bridge/` returns nothing at top level).
- **One boundary, not N.** Every host runtime goes through the same `run_pipe_via_bridge` and the same JSON-safe types, instead of each plugin re-implementing boot / validate / hydrate / dispatch. *Verify:* the Mistral plugin and the Temporal activities both consume `runtime_bridge` rather than duplicating it.
- **No duplication across runtimes.** The lift means the Temporal and Mistral paths share one copy of delivery / trace-flush / hydration / etc. *Verify:* `act_*.py` are wrappers; the logic lives once under `primitives/` (graph+usage assembly lives once in `pipe_run/tracing_assembly.py`).
- **Optional deps stay optional.** Lazy imports keep `pipelex[temporal]` and the Mistral plugin off the import path for DIRECT / plain-Python users. *Verify:* import `run_pipe_via_bridge` with neither extra installed → DIRECT runs; the other modes raise the install-hint errors (`test_dispatch.py`, `test_validation.py`).
- **Not overengineered.** No abstraction was added without a real second consumer: the bridge exists because there are already two host runtimes (Temporal, Mistral) plus plain Python; the primitives were extracted only once two paths shared them; `__init__.py` is empty (no re-export indirection, per project convention); the mode set is a flat enum, not a plugin registry. No speculative interfaces or config.
- **Solid, not a workaround.** Boundary types forbid extras; missing deps fail with actionable messages; the crate path isolates per-call dynamic classes from the global registry; fire-and-forget refuses to run without a delivery target; `trace_context` is honored for DIRECT only (forwarding it to a Temporal mode would merge Pipelex's trace events into the host's graph — the contract forbids that). All covered by the bridge tests.

## Known deferred items (don't re-flag these)

These are intentionally out of scope for this PR; each is recorded so review tooling doesn't re-raise them as new findings. Details in `wip/runtime-bridge/`.

- **Half-built-singleton boot race.** `ensure_pipelex_booted()` closed the write-write race with a double-checked lock. A narrower lock-free read of a half-built singleton mid-`setup()` remains theoretically possible (the singleton is published when `__init__` returns, before the slow `setup()` runs). Low practical exposure — Temporal is not in production. Full mechanism + fix shape: `wip/runtime-bridge/bootstrap-half-built-singleton-race.md`.
- **Unused `PipelexExecutionMode` `@property` helpers.** `requires_pipelex_temporal`, `requires_mistral_workflows_extra`, and `is_fire_and_forget` are tested but not yet consumed by `bridge.py` (which currently inlines the equivalent `match`/identity checks). Kept as a tested, intention-revealing surface; wiring them in is a follow-up, not a bug.

## Downstream impact

The two consumers of the lifted surface — `pipelex-mistralai-workflows` (the `MISTRAL_NATIVE` host package) and the `_workflows` integration branch — are pinned to a pre-extraction `pipelex` and are not broken by this PR landing. The reconciliation they need once this merges to `dev` is sequenced and documented in `wip/distributed-execution/bridge-changes-sibling-repo-reconciliation.md`. No sibling-repo code changes are in this PR.

## Verification

`make agent-check` (ruff, plxt, pyright, mypy) and `make agent-test` both green on this branch.
