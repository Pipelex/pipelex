# runtime-bridge — review follow-ups from PR #959

Triage of the SWE-agent review comments on **PR #959** (`feat: extract framework-agnostic Pipelex runtime bridge`, branch `feature/Runtime-bridge-extraction`). The PR extracts `pipelex/runtime_bridge/` — a host-runtime-agnostic surface (`run_pipe_via_bridge`) that lets Mistral Workflows / raw Temporal / future plugins invoke Pipelex pipes from inside their own activities.

Two review bots left 12 unresolved threads (**greptile-apps** + **cubic-dev-ai**). All 12 were verified against the code. **All are now resolved in the working tree** — the only thing left is replying to / resolving the GitHub threads (see "Remaining" at the bottom).

## 1. Design forks — all resolved

Each was a **confirmed** finding whose resolution was a genuine design choice. Each doc retains its full triage as the record of why.

- **[direct-mode-nested-router-leak.md](direct-mode-nested-router-leak.md)** — ✅ **RESOLVED (Option A).** (greptile P1, + cubic P2 enabler) In `DIRECT` mode, nested controller sub-pipes resolved the *hub default* router and leaked to Temporal when a worker has `[temporal] is_enabled`. Fixed with a `scoped_pipe_router` helper in `hub.py` wrapping `_run_direct` (also resolves cubic's hub.py:615/teardown-clobber). The observer sub-question that gated the fork is written up in [`../observer-and-telemetry/observer-telemetry-posthog.md`](../observer-and-telemetry/observer-telemetry-posthog.md).
- **[graph-context-temporal-contract.md](graph-context-temporal-contract.md)** — ✅ **RESOLVED (Option A).** (greptile P2) `graph_context` was threaded into the `PipeJob` for *all* modes despite the DIRECT-only docstring, and `WfPipeRouter` consumes it. Fixed: `run_pipe_via_bridge` now nulls `graph_context` for the Temporal modes (honoring the contract); docstring corrected. + regression test.
- **[trace-flush-blocking-io.md](trace-flush-blocking-io.md)** — ✅ **RESOLVED (false positive / by-design).** (cubic P2) `flush_trace_events_to_backend` is `async` with blocking boto3/file I/O — but it runs in an *activity*, which is exactly where Temporal allows blocking I/O. No code change. The optional `asyncio.to_thread` throughput-offload note is kept on file for if/when Temporal ships and we profile worker contention.
- **[bridge-error-name-collision.md](bridge-error-name-collision.md)** — ✅ **RESOLVED (renamed).** The near-mirror `PipelexBridgeRuntimeError` (leaf) vs `PipelexRuntimeBridgeError` (base) was renamed: the leaf is now **`PipelexBridgeDispatchError`**. Updated the class, `bridge.py` raises, `test_validation.py`, regenerated `docs/errors/` (old slug removed, new written; no mistral churn), and the `TODOS.md` prose.

## 2. Mechanical fixes — all applied

- **Boot race** — ✅ `pipelex/runtime_bridge/bootstrap.py`. Double-checked locking with a module-level `threading.Lock` (re-check inside the lock). Regression test: `tests/unit/pipelex/runtime_bridge/test_bootstrap_concurrency.py` (threaded barrier; asserts make runs once, no raise).
- **Exceptions caller-facing flag** — ✅ `pipelex/runtime_bridge/exceptions.py`. Added `_authors_caller_facing_message = True` to `MissingPipelexTemporalExtraError` and `MissingMistralWorkflowsPluginError` so the pip-install hint survives STRICT disclosure. Regression test: `test_exceptions_disclosure.py`.
- **streaming.mdx missing import** — ✅ added `import asyncio` to the example's import block.
- **observability.mdx frontmatter id** — ✅ `id: observabilities` → `id: observability`.
- **your-first-workflow.mdx grammar** — ✅ "It coordinate" → "It coordinates".
- **your-first-workflow.mdx broken image** — ✅ removed the missing-PNG image, kept the instruction text.
- **durable-execution.md overgeneralization** — ✅ rewrote the line to distinguish the two durable backends (the `[temporal] is_enabled` flag is the Pipelex-on-Temporal backend only; the Mistral Workflows path runs pipes via the runtime bridge inside Workflows activities).

## Verification

`make agent-check` (ruff, plxt, pyright 0/0/0, mypy) and `make agent-test` (full suite) both green.

## Remaining

Code/docs are done. What's left is the GitHub side, per the `/review-pr-agents` skill: reply on each PR #959 thread (`✅ Fixed` / `➖ False positive`) and resolve them. No threads need to stay open — every fork was decided and applied.
