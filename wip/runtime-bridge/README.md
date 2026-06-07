# runtime-bridge — review follow-ups

Triage of the SWE-agent review comments on **PR #959** (`feat: extract framework-agnostic Pipelex runtime bridge`, branch `feature/Runtime-bridge-extraction`). The PR extracts `pipelex/runtime_bridge/` — a host-runtime-agnostic surface (`run_pipe_via_bridge`) that lets Mistral Workflows / raw Temporal / future plugins invoke Pipelex pipes from inside their own activities.

Two review bots left 12 unresolved threads (**greptile-apps** + **cubic-dev-ai**). All 12 were verified against the code. **All are now resolved in the working tree** — the only thing left is replying to / resolving the GitHub threads (see "Remaining" at the bottom).

## 1. Design forks — all resolved

Each was a **confirmed** finding whose resolution was a genuine design choice. Each doc retains its full triage as the record of why.

- **[direct-mode-nested-router-leak.md](direct-mode-nested-router-leak.md)** — ✅ **RESOLVED (Option A).** (greptile P1, + cubic P2 enabler) In `DIRECT` mode, nested controller sub-pipes resolved the *hub default* router and leaked to Temporal when a worker has `[temporal] is_enabled`. Fixed with a `scoped_pipe_router` helper in `hub.py` wrapping `_run_direct` (also resolves cubic's hub.py:615/teardown-clobber). The observer sub-question that gated the fork is written up in [`../observer-and-telemetry/observer-telemetry-posthog.md`](../observer-and-telemetry/observer-telemetry-posthog.md).
- **[graph-context-temporal-contract.md](graph-context-temporal-contract.md)** — ✅ **RESOLVED (Option A).** (greptile P2) `graph_context` was threaded into the `PipeJob` for *all* modes despite the DIRECT-only docstring, and `WfPipeRouter` consumes it. Fixed: `run_pipe_via_bridge` now nulls `graph_context` for the Temporal modes (honoring the contract); docstring corrected. + regression test.
- **[trace-flush-blocking-io.md](trace-flush-blocking-io.md)** — ✅ **RESOLVED (false positive / by-design).** (cubic P2) `flush_trace_events_to_backend` is `async` with blocking boto3/file I/O — but it runs in an *activity*, which is exactly where Temporal allows blocking I/O. No code change. The optional `asyncio.to_thread` throughput-offload note is kept on file for if/when Temporal ships and we profile worker contention.
- **[bridge-error-name-collision.md](bridge-error-name-collision.md)** — ✅ **RESOLVED (renamed).** The near-mirror `PipelexBridgeRuntimeError` (leaf) vs `PipelexRuntimeBridgeError` (base) was renamed: the leaf is now **`PipelexBridgeDispatchError`**. Updated the class, `bridge.py` raises, `test_validation.py`, regenerated `docs/errors/` (old slug removed, new written; no mistral churn), and the `TODOS.md` prose.

## 2. Mechanical fixes — all applied

- **Boot race** — ✅ `pipelex/runtime_bridge/bootstrap.py`. Double-checked locking with a module-level `threading.Lock` (re-check inside the lock). Regression test: `tests/unit/pipelex/runtime_bridge/test_bootstrap_concurrency.py` (threaded barrier; asserts make runs once, no raise). **Follow-up (PR #966 review):** this closed the write-write race but not a lock-free read of a half-built singleton mid-`setup()` — **now also fixed** via Approach B (the bridge gates on `Pipelex.is_fully_booted()`; an instance-level `is_ready` is published only at the end of `make()`). See §3 / [`bootstrap-half-built-singleton-race.md`](bootstrap-half-built-singleton-race.md).
- **Exceptions caller-facing flag** — ✅ `pipelex/runtime_bridge/exceptions.py`. Added `_authors_caller_facing_message = True` to `MissingPipelexTemporalExtraError` and `MissingMistralWorkflowsPluginError` so the pip-install hint survives STRICT disclosure. Regression test: `test_exceptions_disclosure.py`.
- **streaming.mdx missing import** — ✅ added `import asyncio` to the example's import block.
- **observability.mdx frontmatter id** — ✅ `id: observabilities` → `id: observability`.
- **your-first-workflow.mdx grammar** — ✅ "It coordinate" → "It coordinates".
- **your-first-workflow.mdx broken image** — ✅ removed the missing-PNG image, kept the instruction text.
- **durable-execution.md overgeneralization** — ✅ rewrote the line to distinguish the two durable backends (the `[temporal] is_enabled` flag is the Pipelex-on-Temporal backend only; the Mistral Workflows path runs pipes via the runtime bridge inside Workflows activities).

## 3. PR #966 pre-landing review

A later `/review` pass on PR #966 (the bridge + the trace-event read hardening). One deferred item plus four cheap hardening fixes applied to the working tree.

- **Bootstrap half-built-singleton race** — ✅ **applied (P1)**, see [`bootstrap-half-built-singleton-race.md`](bootstrap-half-built-singleton-race.md). The #959 lock closed the write-write race; this closes the remaining lock-free read of a mid-`setup()` singleton. Approach B (instance-level `is_ready`, gated via `Pipelex.is_fully_booted()`, published only at the end of `make()`) — chosen over a module-global flag so the existing `teardown_if_needed()` lifecycle auto-resets it. Regression tests added (mid-setup window + setup-failure re-boot).
- **`library_id` widened** — ✅ `bridge.py` + `primitives/submitter_hydration.py`. Dropped the `uuid4().hex[:8]` truncation (32 bits) to full hex. `open_library` silently *reuses* a colliding id (`library_manager.py:148-149`), so a 32-bit collision between two overlapping calls would share and prematurely tear down one library; full hex matches the collision-safe Temporal path (full `workflow_id`).
- **`act_assemble_graph` comment corrected** — ✅ the lifted primitive catches only a specific exception tuple, so the old "swallows every failure / no error ever crosses the boundary" comment was stale; reworded to say expected failures degrade to None while programming bugs deliberately propagate (pinned by `test_propagates_unexpected_keyerror`).
- **Scoped-library open guarded** — ✅ `bridge.py::_scoped_library_for_crate` now opens the library inside the `try` (with a `library_opened` flag) so a throw between open and yield can't leak the manager entry — matches the sibling `rehydrate_pipe_output_with_crate`.
- **Input decode wrapped** — ✅ `bridge.py` decodes `library_crate_dump` / `delivery_assignment_dump` once, translating raw `pydantic.ValidationError` into `PipelexBridgeDispatchError` so a malformed dump no longer escapes the entry point as a non-`PipelexError`; also removes the double-decode of the delivery dump. `_validate_input` now takes the decoded assignment (its unit tests updated).

`make agent-check` (pyright 0/0/0, mypy clean) and `tests/unit/pipelex/runtime_bridge/` green after these.

## Verification

`make agent-check` (ruff, plxt, pyright 0/0/0, mypy) and `make agent-test` (full suite) both green.

## 4. PR #969 review rounds (live PR)

PR #969 is the live PR (#959 and #966 closed). Successive bot rounds (greptile / cubic / codex) each re-examined the prior round's fixes plus new surface. Round-4 dispositions:

- **Keyed tracers through the bridge** (`bridge.py:179`, greptile P1 + cubic P2) — ✅ **RESOLVED (loud guard).** Full triage + the deferred structural option in [`bridge-keyed-tracer-unsupported.md`](bridge-keyed-tracer-unsupported.md). `lookup_key` is kept and a boundary guard rejects a divergent `tracer_key` so it can never silently drop graph/cost data.
- **Temporal blocking `workflow_id`** (`bridge.py:342`, codex P2 + cubic P1) — ✅ **RESOLVED (real fix).** Blocking reported the bare `pipeline_run_id`; the workflow is actually started with `make_workflow_id(...)`, which prefixes in non-NORMAL run modes (`ut-`/`ci-`/`cc-`/`cct-`). The bridge now reports `make_workflow_id(...)` — the same id fire-and-forget returns from `start()`, single source of truth. In `RunMode.NORMAL` (prod) the prefix is empty, so behavior is unchanged there. Wiring test: `tests/unit/pipelex/runtime_bridge/test_temporal_blocking_workflow_id.py`; prefix table covered by `tests/unit/pipelex/temporal/test_workflow_id_construction.py`.
- **trace_flush pre-dedup** (`trace_flush.py:28`, cubic P2) — ➖ **False positive.** Dedup is a **read-side** contract: `EventLogProtocol.read_events` returns events deduplicated by `(workflow_id, writer_id, event_type, sequence)`, and the DynamoDB backend is write-idempotent via PK+SK ("natural deduplication for Temporal replay re-emissions"). NDJSON appends on retry but `read_events` collapses duplicates on assembly. The proposed pre-dedup key also **omits `pipeline_run_id`**, so it would wrongly collapse identical sequences across different runs. No code change. (Related async/blocking-IO note already on file: [`trace-flush-blocking-io.md`](trace-flush-blocking-io.md).)
- **Mistral-workflows docs** (`index.md:29` cubic P2, `choosing-a-backend.md:8` cubic P3) — ✅ **RESOLVED (accuracy).** "Automatic activity retries — each leaf operator retries independently" overclaimed: in `direct` mode the whole pipe runs in one host activity. Reworded to be mode-aware (`direct` retries as a unit; `mistral_native` retries leaves independently). The "replay" guarantee line was reworded to state replay re-runs the workflow from history reusing stored activity results, not re-executing completed activities.

## Remaining

Code/docs are done. What's left is the GitHub side, per the `/review-pr-agents` skill: reply on each PR #969 thread (`✅ Fixed` / `➖ False positive`) and resolve them. No threads need to stay open — every fork was decided and applied.
