# PR #959 — Framework-agnostic Pipelex runtime bridge (reviewer's guide)

What this PR does, how, and why it's the right shape. Base branch: `dev`.

The diff looks large (~140 files) but the **code** core is small and concentrated. Concentrate review on:

- `pipelex/runtime_bridge/` — the new package (the point of the PR)
- `pipelex/temporal/tprl_pipe/act_*.py` — the thin-wrapper rewiring
- `pipelex/hub.py` — the `scoped_pipe_router` addition
- `tests/{unit,integration}/pipelex/runtime_bridge/`

**Out of scope for review — please disregard:** the `/workflows` skill under `.claude/skills/workflows/` accounts for most of the diff's line count but is **not part of this PR's work**. It was vendored from Mistral's own (drafty) Workflows skill and adapted for Claude Code; it rode along on this branch only for convenience. Do not review it as PR content. Internal triage notes under `wip/` are likewise not review material.

## What it does

Adds one host-runtime-agnostic surface — `pipelex/runtime_bridge/` — through which any embedding runtime (Mistral Workflows, a raw Temporal worker, a future plugin, or plain Python) invokes a Pipelex pipe from inside its own activity. Single entry point:

```python
from pipelex.runtime_bridge.bridge import run_pipe_via_bridge, PipelexPipeRunInput
output = await run_pipe_via_bridge(PipelexPipeRunInput(pipe_code=..., inputs={...}, execution_mode=...))
```

Input and output are JSON-safe pydantic models (`PipelexPipeRunInput` / `PipelexPipeRunOutput`, both `extra="forbid"`), so the boundary survives a serialization hop across a worker/activity without leaking Pipelex internals.

## Execution modes (`execution_mode.py`)

The caller chooses how the pipe runs via `PipelexExecutionMode`:

- `DIRECT` — in-process, no Temporal; the activity blocks until the pipe completes. Fastest, simplest; works even inside a Temporal-enabled worker (forces local execution).
- `TEMPORAL_BLOCKING` — dispatch the pipe as a Pipelex Temporal workflow and await it. Needs `pipelex[temporal]`.
- `TEMPORAL_FIRE_AND_FORGET` — dispatch and return the `workflow_id` immediately; completion arrives out-of-band via `DeliveryAssignment` (webhook/storage). Needs `pipelex[temporal]` + a `delivery_assignment_dump`.
- `MISTRAL_NATIVE` — decompose the pipe into native Mistral Workflows primitives (controllers → child workflows, leaves → activities). Needs the `pipelex-mistralai-workflows` package.

Mode-specific dependencies are pulled in by **lazy import inside the matching branch only** — the bridge module imports nothing host-specific at top level. So DIRECT runs with neither extra installed, and a missing extra raises a precise, install-hint error (`MissingPipelexTemporalExtraError` / `MissingMistralWorkflowsPluginError`) rather than an `ImportError` at module load.

## How a call flows (`bridge.py::run_pipe_via_bridge`)

1. `ensure_pipelex_booted()` — idempotent, thread-safe boot; adopts an externally-created singleton if one already exists.
2. `_validate_input` — mode-specific guards (e.g. fire-and-forget must carry a delivery assignment, else completion would be silently dropped).
3. `_scoped_library_for_crate` — if the caller passed a `library_crate_dump`, open a **per-call scoped library** with its own `ClassRegistry`, load it from the crate, tear it down on exit. This is what lets a stateless / multi-tenant worker run a pipe whose definition travels in the request, without leaking dynamic concept classes into the global registry.
4. `build_pipe_job_from_input` — hydrate a `PipeJob` (working memory from inputs, job metadata, optional graph context).
5. `match execution_mode:` — dispatch to that mode's runner.

## The primitives lift (`runtime_bridge/primitives/`)

The framework-agnostic bodies behind the Temporal activities (graph assembly, delivery, trace flush, hydration, pipe classification, submitter hydration) were moved verbatim out of `pipelex.temporal` into `runtime_bridge.primitives`. The `pipelex/temporal/tprl_pipe/act_*.py` files are now **thin `@activity.defn` wrappers** that decode their arg and delegate to the shared primitive (see `act_assemble_graph.py`). The Mistral-native path calls the same primitives. Behaviour-neutral: only the home of the logic changed.

## Why this is the right shape (claims a reviewer can check)

- **Separation of concerns.** "How a host invokes a pipe" (bridge) is now distinct from "how Pipelex executes a pipe" (`pipe_run` / `pipe_controllers`) and from "Temporal SDK glue" (`pipelex.temporal`). *Verify:* `runtime_bridge/` has no `temporalio` / `mistralai` import at module top level — host SDKs appear only inside lazy-import branches (`grep -rn "import temporalio\|import mistralai" pipelex/runtime_bridge/` returns only docstring prose).
- **One boundary, not N.** Every host runtime goes through the same `run_pipe_via_bridge` and the same JSON-safe types, instead of each plugin re-implementing boot / validate / hydrate / dispatch. *Verify:* the Mistral plugin and the Temporal activities both consume `runtime_bridge` rather than duplicating it.
- **No duplication across runtimes.** The lift means the Temporal and Mistral paths share one copy of graph-assembly / delivery / etc. *Verify:* `act_*.py` are wrappers; the logic lives once under `primitives/`.
- **Optional deps stay optional.** Lazy imports keep `pipelex[temporal]` and the Mistral plugin off the import path for DIRECT / plain-Python users. *Verify:* import `run_pipe_via_bridge` with neither extra installed → DIRECT runs; the other modes raise the install-hint errors (`test_dispatch.py`, `test_validation.py`).
- **Not overengineered.** No abstraction was added without a real second consumer: the bridge exists because there are already two host runtimes (Temporal, Mistral) plus plain Python; the primitives were extracted only once two paths shared them; `__init__.py` is empty (no re-export indirection, per project convention); the mode set is a flat enum, not a plugin registry. No speculative interfaces or config.
- **Solid, not a workaround.** Boundary types forbid extras; missing deps fail with actionable messages; the crate path isolates per-call dynamic classes from the global registry; fire-and-forget refuses to run without a delivery target. All covered by the bridge tests.

## Review follow-ups already addressed

The SWE-review threads on this PR are all resolved (commit `5e6c86c2`); the triage and rationale live in `wip/runtime-bridge/README.md`. Notably: DIRECT mode now scopes its in-process router (`scoped_pipe_router`) so nested sub-pipes can't leak to Temporal; `graph_context` is honored for DIRECT only; `ensure_pipelex_booted` is race-safe.

## Verification

`make agent-check` (ruff, plxt, pyright, mypy) and `make agent-test` both green on this branch.
