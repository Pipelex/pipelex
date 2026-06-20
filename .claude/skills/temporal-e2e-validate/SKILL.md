---
name: temporal-e2e-validate
description: >
  Full end-to-end validation of Temporal distributed execution (Phases 2-5 +
  v1 routing + v2 queue options / worker-runtime profiles). Two modes:
  (1) pytest against a real Temporal server for detailed assertions on all
  test cases, and (2) true 3-process setup (server + separate worker process
  + submitter) that validates the actual deployment topology including
  cross-process serialization, LibraryCrate propagation, deferred hydration,
  concurrent isolation, image payload storage, cross-worker graph
  tracing with GraphSpec assembly, and cross-worker cost-report assembly
  (runner-side usage aggregated into a single submitter cost report, validated
  cheaply via the hidden `--dry-run --mock-usage` trigger). Step 8 validates v1 per-activity routing.
  Step 9 validates v2 per-queue submitter options (timeouts, retry,
  rate-limit), per-handle option overrides, named worker-runtime profiles
  selected via `--profile`, and the strict `--task-queue` CLI typo check
  with "did you mean?" suggestion. Mode 1 also folds in the error-handling
  suite (activity error boundary, workflow error-report full chain, local
  parity arm); Mode 2 Tiers 13-16 validate that a worker-side failure — from an
  LLM, extract, image-gen, or batched child-workflow activity — carries
  a structured `ErrorReport` across the activity -> workflow -> submitter
  boundary. Tier 17 validates that a `--temporal --dry-run` run dispatches the
  real inference activities and mocks INSIDE them (run mode orthogonal to
  backend — no API keys, no storage IO, zero-token suppressed usage).
  Use when the user says "validate temporal", "e2e temporal",
  "temporal regression", "temporal validation", "3-process test", "full temporal
  test", "validate phases", "image temporal", "queue options", "runtime profile",
  "validate error handling", "error report", "error propagation",
  "cost report", "distributed cost", "mock usage",
  or wants comprehensive verification that distributed execution works
  end-to-end. Also use proactively after changes to LibraryCrate, deferred
  hydration, ClassRegistry scoping, graph tracing, image generation activities,
  content storage, queue options resolution, worker-runtime profiles,
  usage / cost reporting, the `--costs` / `--mock-usage` flags,
  error classification / `ErrorReport` / the Temporal error boundary, or
  Temporal workflow code.
allowed-tools:
  - Bash(tmux *)
  - Bash(curl *)
  - Bash(.venv/bin/pytest *)
  - Bash(.venv/bin/pipelex *)
  - Bash(ls *)
  - Bash(which *)
  - Bash(open *)
  - Bash(cat *)
  - Bash(.venv/bin/python *)
  - Bash(grep *)
  - Bash(sort *)
  - Bash(head *)
  - Bash(tail *)
  - Bash(temporal *)
  - Bash(jq *)
  - Bash(timeout *)
  - Bash(pkill *)
  - Bash(sleep *)
  - Bash(echo *)
  - Bash(seq *)
---

# Temporal E2E Validation Suite

This skill validates that Pipelex pipelines execute correctly when distributed across
Temporal workers — separate processes that receive serialized work, run pipes, and return
results. It covers the full chain: shipping pipe definitions to the worker (Phase 2),
deserializing dynamic concepts the worker has never seen (Phase 3), isolating concurrent
workflows so they don't corrupt each other (Phase 4), assembling an execution graph
from trace events emitted across workers (Phase 4.5), and verifying that image-heavy
pipelines (image generation, image-to-LLM flow) don't blow up Temporal's payload
limits by ensuring images are stored at the activity level.

## Important: surface results immediately

After each command completes, **immediately tell the user** the outcome in plain text —
PASS/FAIL, what it means, output paths. Do NOT silently move on to the next command.
The user sees collapsed tool outputs by default and relies on your text messages.

Use multi-line formatting with clean indentation — never cram everything onto one line:

```
Tier 1 PASS
  The worker received the pipe definitions and executed a 2-step sequence correctly.
  Output: results/native_text_sequence_output_01/
  Graph:  results/native_text_sequence_output_01/reactflow.html
```

For failures, include the error message and what it means:

```
Tier 2 FAIL
  KajsonDecoderError: Class 'Greeting' not found
  The worker tried to deserialize WorkingMemory before registering dynamic concepts.
  Check worker output: tmux capture-pane -t temporal-worker-router -p -S -200
  (or tmux capture-pane -t temporal-worker-runner / temporal-worker depending on setup)
```

---

## Timeouts policy — REQUIRED for every command

A hung Temporal test will lock the session and consume the agent's wall time until the
user interrupts. Workers, workflow polls, and gRPC retries will happily wait forever.
**Every** `.venv/bin/pytest` and `.venv/bin/pipelex run bundle` invocation in this skill
runs under a hard shell `timeout` and, for pytest, under `--timeout=N` per test as well.
`pytest --timeout=N` alone is not sufficient — it caps a single test, not fixture
setup/teardown, so a broken session-scoped fixture can still hang forever without the
shell cap.

**Defaults to use (apply unless a step explicitly overrides):**

| Command kind | Shell cap | Per-test cap |
|---|---|---|
| Single dry-run pipeline (`pipelex run bundle ... --dry-run --mock-inputs`) | `timeout 120` | — |
| Two concurrent dry-run pipelines (isolation pairs) | `timeout 180` | — |
| Live pipeline (`pipelex run bundle ... --temporal` without `--dry-run`) | `timeout 600` | — |
| Repro/diagnostic script (`.venv/bin/python <path-to-script>.py`) | `timeout 120` | — |
| Pytest folder (dry, `library_crate/` or single module) | `timeout 300` | `--timeout=90` |
| Pytest single test class/case (dry) | `timeout 180` | `--timeout=60` |
| Pytest folder (live, real LLM/img-gen) | `timeout 900` | `--timeout=300` |

**Form to use everywhere:**

```bash
timeout 300 .venv/bin/pytest -x -v tests/integration/pipelex/temporal/library_crate/ \
  -m temporal --temporal-server local --timeout=90 2>&1 | tail -80
```

```bash
timeout 120 .venv/bin/pipelex run bundle <bundle> --pipe <pipe> \
  --temporal --dry-run --mock-inputs --no-logo --graph 2>&1 | tail -15
echo "EXIT=$?"
```

**If a command times out (exit 124 from `timeout`) or behaves as if hung, the response is
ALWAYS the same:**

1. Capture worker output: `tmux capture-pane -t temporal-worker-router -p -S -200`
   and `tmux capture-pane -t temporal-worker-runner -p -S -200` (or
   `temporal-worker` for the single-worker setup). Quote the actual error.
2. Kill zombies before retrying: `pkill -f "pipelex.temporal.worker_cli"`,
   `pkill -f "pytest.*temporal"`. Stale workers from a previous timed-out run
   will swallow new dispatches and make every subsequent step look hung.
3. Diagnose root cause from the captured output. Do **not** raise the timeout
   and rerun blind — that wastes another minute and produces the same hang. The
   "Interpreting failures" table at the bottom of this skill maps common error
   strings to causes.

---

## Prerequisites

```bash
which tmux && echo "ok" || echo "MISSING: brew install tmux"
which temporal && echo "ok" || echo "MISSING: brew install temporal"
.venv/bin/python -c "import temporalio; print(f'temporalio {temporalio.__version__}')"
```

---

## Mode 1: Automated Test Suite (pytest)

Runs integration tests against a real Temporal server (localhost:7233), but the worker
runs in-process — no separate worker needed. This is the fast path for catching
regressions.

### Step 1: Ensure the Temporal dev server is running

```bash
curl -s http://localhost:8233 > /dev/null 2>&1 && echo "running" || echo "not running"
```

If not running:

```bash
tmux new-session -d -s temporal-server 'temporal server start-dev'
sleep 3
curl -s http://localhost:8233 > /dev/null 2>&1 && echo "running" || echo "FAILED"
```

Do NOT start if already running — it will fail with a bind error.

### Step 2: Run the tests

The conftest auto-registers the Pipelex custom search attributes listed in
`pipelex.system.configuration.config_temporal.BUILTIN_SEARCH_ATTRIBUTES` on the first
session that hits a fresh dev server. No manual setup needed.

**Dry mode (fast, no LLM costs):**

```bash
timeout 300 .venv/bin/pytest -v tests/integration/pipelex/temporal/library_crate/ \
  -m temporal --temporal-server local --timeout=90 2>&1 | tail -80
```

**Live mode (real LLM calls):**

```bash
timeout 900 .venv/bin/pytest -v tests/integration/pipelex/temporal/library_crate/ \
  -m temporal --temporal-server local --pipe-run-mode live --timeout=300 2>&1 | tail -80
```

Note on `-x`: omitted here so we see the full failure surface, not just the first hang.
If you want the classic stop-on-first-failure behavior, add `-x` back — but expect to
diagnose root cause from the first failure before retrying.

### Step 2b: Run the error-handling tests

These verify that a Pipelex failure crosses the Temporal boundary carrying a
structured `ErrorReport` (`error_category` / `error_domain` / `retryable` /
`model` / `provider` / `user_action`), with local/Temporal parity. They live
*outside* `library_crate/`, so Step 2 does not pick them up. The LLM call is
mocked in every one of these tests — no API keys, no inference cost.

```bash
# Error-handling tests — Temporal boundary (real server, in-process worker, mocked LLM)
timeout 300 .venv/bin/pytest -v \
  tests/integration/pipelex/temporal/test_activity_error_boundary.py \
  tests/integration/pipelex/temporal/test_wf_pipe_run_failure_path.py \
  tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py \
  -m temporal --temporal-server local --timeout=90 2>&1 | tail -60
```

```bash
# Error-handling tests — local parity arm (no Temporal server, mocked LLM)
timeout 180 .venv/bin/pytest -v \
  tests/integration/pipelex/error_handling/ --timeout=60 2>&1 | tail -40
```

The local arm is **not** marked `temporal`, so it must run as its own
invocation — a `-m temporal` filter would deselect it.

### Step 3: Report results

Tell the user what each suite validated and whether it passed. Here is what the suites test:

- **TestWfLibraryCrate** — Can a worker receive a "crate" (a portable bundle of pipe
  definitions) and execute a PipeSequence from it? Also tests that submitting *without* a
  crate correctly fails with `PipeNotFoundError`.
- **TestWfDeferredHydration** — When a pipe creates a brand-new concept type at runtime
  (e.g. `Greeting` with `message` and `language` fields), can the worker deserialize
  WorkingMemory that contains instances of that concept, even though the worker has never
  seen the class before?
- **TestWfConcurrentConceptIsolation** — Two workflows run simultaneously on the same
  worker, both defining a concept called `Result` — but with different fields (`score, label`
  vs `value, confidence, is_valid`). Does each workflow get the right version, or do they
  clobber each other?
- **TestWfConcurrentPipeIsolation** — Same idea, but for pipes: two workflows both define
  a pipe called `shared_step` with different prompts. Does each workflow execute its own
  version?
- **TestWfMultiConceptIsolation** — Worst case: two workflows define *two* overlapping
  concepts each (`Profile` + `Summary`) with incompatible structures, running across 6
  concurrent workflows.
- **TestWfPipeParallel** — A PipeParallel controller dispatches branches as concurrent
  child workflows. Do the branches execute independently and merge correctly?
- **TestWfPipeCondition / PipeBatch / PipeCompose / CombinedPipeline** — Controller
  coverage for condition routing, fan-out/fan-in, composition, and nested controller
  combinations.

For Step 2b (error-handling), here is what the suites validate:

- **TestActivityErrorBoundary** — A real activity failure (LLM and non-LLM) is caught
  by the `convert_pipelex_errors` boundary and surfaces a classified `ErrorReport` on
  the workflow side, with the correct `non_retryable` flag derived from the error
  category.
- **TestWfPipeRunFailurePath** — When the pipe router fails inside the workflow,
  delivery still fires with `DeliveryStatus.FAILED` (and `pipe_output` unset), then the
  failure re-raises.
- **TestWorkflowErrorReportFullChain** — The `ErrorReport` survives the full
  activity → workflow → submitter Temporal round-trip with `error_category` /
  `retryable` / `model` / `provider` / `user_action` intact — the recovered report
  carries the real failure message, not the generic `"Failed to execute workflow"`.
- **TestErrorReportLocalFullChain** — The local (non-Temporal) parity arm: the same
  failing pipe run through `PipeRouter` directly. Both arms assert the same
  `ErrorReportParityTestData` constants, so local/Temporal `ErrorReport` parity holds
  by construction.

**Known xfails:** Some controller execution tests fail in dry-run mode because
`StuffArtefact` objects can't serialize through Temporal's data converter. The crate
structure tests pass. These xfails will resolve once StuffArtefact serialization is fixed.

The test `test_missing_crate_fails_pipe_resolution` is a **negative test** — it intentionally
submits without a crate. The Temporal warning `Failed activation on workflow` with
`RuntimeError: No current library set` is expected.

---

## Mode 2: True 3-Process Validation

The real deployment test: three separate OS processes — Temporal server, worker, and
submitter — with no shared memory. The worker has its own Python runtime, its own
`sys.modules`, its own `ClassRegistry`. This is the only way to catch bugs an in-process
worker (Mode 1) cannot — e.g. the worker failing to deserialize a PipeJob because concept
classes aren't registered, the Kajson decoder bypassing class lookup, or the Temporal
data converter silently dropping fields.

Mode 2 is a battery of tiers and scenarios. It is long, and most invocations need only
part of it — so the procedure lives in **reference files under `references/`**, each
loaded only for the work at hand. Read them as needed:

| Reference file | Covers | Read it when |
|---|---|---|
| `references/mode-2-setup.md` | Steps 1–2: Temporal server + worker processes; run-mode (dry vs live) | **Always — start here.** Every other Mode 2 file assumes the server + worker(s) are already up. |
| `references/mode-2-tiers.md` | Steps 3–7: Tiers 1–16 (sequence, hydration, parallel, image gen/flow, isolation, cross-worker usage + cost report, object gen, extract, CV batch, error propagation), codec, final report | Validating core distributed execution, cost reporting, or running the full suite. |
| `references/routing-battery.md` | Step 8: v1 `activity_queues` per-activity / per-handle routing (Tiers 10a–10c) | Validating that `activity_queues` isolates workers. Opt-in. |
| `references/queue-options-battery.md` | Step 9: v2 per-queue options, per-handle overrides, rate limits, worker-runtime profiles, CLI typo check (Scenarios A–F) | Validating queue options / worker-runtime profiles. Opt-in. |

**Choosing what to run** — match the request, then read only those files:

- "validate temporal" / "full temporal test" / a broad regression check → `mode-2-setup.md`, then `mode-2-tiers.md`; offer the two batteries as opt-in extras.
- "validate temporal error handling" / "error report" / "error propagation" → Mode 1 Step 2b above (the precise pytest assertions) **plus** `mode-2-setup.md` + `mode-2-tiers.md` Step 5f (Tiers 13–16, cross-process).
- "dry run temporal" / "dry-run dispatch" / "leaf mock" → `mode-2-setup.md` + `mode-2-tiers.md` Step 5g (Tier 17: DRY honors the backend — dispatch + mock inside the activity, no keys needed), plus the Mode-1 pytest `tests/integration/pipelex/temporal/tracing/test_dry_run_dispatches_and_mocks.py`.
- "cost report" / "distributed cost" / "mock usage" → `mode-2-setup.md` (split workers), then `mode-2-tiers.md` Step 5b' (Tier 8b). This routing is **scope-aware**: once a request has landed here (via one of those three triggers), read the scope manifest at the top of Step 5b' and run the arms it selects:
    - **default** (bare "cost report" / "distributed cost" / "mock usage") → the free, deterministic mock arms only (`--dry-run --mock-usage`); no live spend.
    - **explicit spend opt-in** — the canonical token `full` (aliases `thorough`, `every`, `with-spend`) qualifying the cost request (e.g. "cost reporting full", "cost report — every arm") → **every** cost arm, real spend authorized: mock primary + cross-child + CSV cross-check + the `--no-costs` negative gate + live LLM + live img-gen + live extract. Run them all and report PASS/FAIL per arm. Do **not** treat bare "live" or "all" as a spend opt-in — they're too easily incidental ("live" also collides with the default mock arm, which already runs in LIVE mode); if that's the only signal, confirm with the user before spending real money.
- "queue options" / "runtime profile" / "routing" → `mode-2-setup.md`, then `routing-battery.md` and/or `queue-options-battery.md`.
- Anything image-related → `mode-2-setup.md` + `mode-2-tiers.md` Tiers 4–5, run **live** — dry-run cannot surface payload-size bugs.

The **Timeouts policy** and the **"surface results immediately"** rule above apply to
every command in every reference file. The **Interpreting failures** table and **Bundle
reference** below cover all of Mode 2 — keep them in mind while running any reference file.

---

## Cleanup

Propose these to the user — do NOT run them automatically:

- Kill tmux sessions: `tmux kill-session -t temporal-worker-router` / `tmux kill-session -t temporal-worker-runner` (or `tmux kill-session -t temporal-worker` if you used the single full worker) / `tmux kill-session -t temporal-server`. If any of Tiers 13–16 ran, also kill `temporal-worker-err` and confirm `.env` is clean (`grep tier-err .env` returns nothing). A blanket `pkill -f "pipelex.temporal.worker_cli"` clears any stray worker process.
- Clean results directory: `rm -rf results/`
- Clean trace files: `rm -rf .pipelex/traces/`
- Remove temporary override if still present: `.venv/bin/python -c "from pathlib import Path; Path('.pipelex/pipelex_temporary_override.toml').unlink(missing_ok=True)"`

Leave the server running if the user plans to iterate.

---

## Interpreting failures

| Error | What it means |
|-------|--------------|
| `PipeNotFoundError` on worker | The LibraryCrate didn't arrive or wasn't loaded — the worker can't find the pipes it's supposed to run |
| `KajsonDecoderError: Class 'X' not found` | The worker tried to deserialize data containing a dynamic concept before registering that concept's class — hydration order bug |
| `RuntimeError: Failed decoding arguments` | Temporal's data converter can't deserialize the PipeJob on the worker — usually a serialization format issue |
| `WorkflowFailureError` wrapping `TemporalError` | The pipe itself failed during execution — read the inner error for the real cause |
| Submitter shows `"Failed to execute workflow ..."` with no inner detail (Tier 13–16) | The `ErrorReport` did not cross the boundary — submitter-side report recovery (`recover_error_report` / `WorkflowExecutionError`) is broken, or the activity bridge didn't pack the report into `ApplicationError.details` |
| Tier 13–16 run exits 0 (success) instead of failing | A healthy worker is still polling `temporal_task_queue` and stole the activity (kill all workers, keep only `temporal-worker-err`); or the worker booted before `.env` was tampered — it captures env at boot, so it must be started *after* the `cat >> .env` step and *before* `.env` is restored |
| `AssertionError: StructuredContent missing field` | Per-workflow ClassRegistry isolation failed — the worker used the wrong concept class (from another workflow's definitions) |
| Submitter hangs indefinitely | The worker crashed during deserialization — check `tmux capture-pane -t temporal-worker-router -p -S -200` (and the runner session, or `temporal-worker` for the single-worker setup) |
| Both concurrent jobs succeed but wrong data | ContextVar leak between workflows — per-workflow scoping is broken, one workflow's class definitions bled into the other |
| No `reactflow.html` generated | GraphSpec assembly failed — either tracing is disabled in `pipelex.toml` or NDJSON events weren't emitted by the worker |
| `PayloadSizeWarning` in worker logs | Image data (base64) is being passed inline through Temporal payloads instead of being stored at the activity level — the fix is to call storage in the image generation activity before returning results |
| `NotImplementedError` during image generation | The image generation or content storage path isn't wired up for the Temporal execution path — activity-level storage is missing |
| Payload too large / `DataConverterError` on image pipes | Raw image bytes exceed Temporal's payload size limit (~2MB default) — images must be stored and referenced by URI, not passed inline |
| `ImageContent` missing or has no `uri` field | The image generation activity returned raw image data instead of a stored `ImageContent` with a storage URI |
| Codec enabled but no storage files | Payloads are below the threshold (1MB default) — expected in dry-run mode where mock data is small. Run live mode for realistic payload sizes |
| `FileNotFoundError` in codec decode | The codec is trying to load a payload from storage that doesn't exist — storage root path may be misconfigured or files were cleaned up mid-run |

---

## Bundle reference

**Crate/isolation bundles** — in `tests/integration/pipelex/temporal/library_crate/`:

| Bundle | What it tests | Main pipe |
|--------|--------------|-----------|
| `native_text_sequence.mthds` | Basic crate propagation (native Text, 2 steps) | `native_text_sequence` |
| `dynamic_concept_sequence.mthds` | Deferred hydration (Greeting concept created at runtime) | `dynamic_greeting_sequence` |
| `conflict_concept_alpha.mthds` | Concept isolation — Result(score, label) | `alpha_pipeline` |
| `conflict_concept_beta.mthds` | Concept isolation — Result(value, confidence, is_valid) | `beta_pipeline` |
| `conflict_pipe_alpha.mthds` | Pipe isolation — shared_step with alpha prompt | `pipe_alpha_pipeline` |
| `conflict_pipe_beta.mthds` | Pipe isolation — shared_step with beta prompt | `pipe_beta_pipeline` |
| `multi_concept_alpha.mthds` | Multi-concept isolation — Profile(name, age) + Summary(headline, body) | `multi_alpha_pipeline` |
| `multi_concept_beta.mthds` | Multi-concept isolation — Profile(title, department, level) + Summary(content) | `multi_beta_pipeline` |
| `temporal_parallel.mthds` | PipeParallel — concurrent child workflows (ToneAnalysis + LengthAnalysis) | `temporal_parallel_sequence` |
| `temporal_batch.mthds` | PipeBatch — fan-out to per-item child workflows | `temporal_batch_sequence` |
| `temporal_condition.mthds` | PipeCondition — conditional routing via child workflow | `temporal_condition_sequence` |
| `temporal_compose.mthds` | PipeCompose — operator composition + deferred hydration | `temporal_compose_sequence` |
| `temporal_combined.mthds` | Nested PipeParallel + PipeCondition | `temporal_combined_pipeline` |
| `large_payload_sequence.mthds` | Codec stress test — 3-step verbose sequence accumulating large WorkingMemory | `large_payload_sequence` |
| `cv_batch_screening.mthds` | Deeply-nested controller stack (PipeSequence -> PipeSequence + PipeBatch -> PipeSequence) over PipeExtract + PipeLLM. Inputs JSON: `cv_batch_screening_inputs.json` | `batch_analyze_cvs_for_job_offer` |

**Image payload bundles** — in `tests/integration/pipelex/pipes/pipelines/`:

| Bundle | What it tests | Main pipe |
|--------|--------------|-----------|
| `crazy_image_generation.mthds` | Image generation pipeline — LLM imagines scene + PipeImgGen renders it, custom ImagePrompt concept | `generate_crazy_image` |
| `test_image_out_in.mthds` | Image flow — PipeImgGen generates image, then PipeLLM (vision) describes it | `image_out_in` |
