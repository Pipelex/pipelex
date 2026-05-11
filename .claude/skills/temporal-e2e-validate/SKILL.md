---
name: temporal-e2e-validate
description: >
  Full end-to-end validation of Temporal distributed execution (Phases 2-5 +
  v1 routing + v2 queue options / worker-runtime profiles). Two modes:
  (1) pytest against a real Temporal server for detailed assertions on all
  test cases, and (2) true 3-process setup (server + separate worker process
  + submitter) that validates the actual deployment topology including
  cross-process serialization, LibraryCrate propagation, deferred hydration,
  concurrent isolation, image payload storage, and cross-worker graph
  tracing with GraphSpec assembly. Step 8 validates v1 per-activity routing.
  Step 9 validates v2 per-queue submitter options (timeouts, retry,
  rate-limit), per-handle option overrides, named worker-runtime profiles
  selected via `--profile`, and the strict `--task-queue` CLI typo check
  with "did you mean?" suggestion.
  Use when the user says "validate temporal", "e2e temporal",
  "temporal regression", "temporal validation", "3-process test", "full temporal
  test", "validate phases", "image temporal", "queue options", "runtime profile",
  or wants comprehensive verification that distributed execution works
  end-to-end. Also use proactively after changes to LibraryCrate, deferred
  hydration, ClassRegistry scoping, graph tracing, image generation activities,
  content storage, queue options resolution, worker-runtime profiles, or
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
  - Bash(temporal *)
  - Bash(jq *)
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

**Dry mode (fast, no LLM costs):**

```bash
.venv/bin/pytest -x -v tests/integration/pipelex/temporal/library_crate/ \
  -m temporal --temporal-server local 2>&1
```

**Live mode (real LLM calls):**

```bash
.venv/bin/pytest -x -v tests/integration/pipelex/temporal/library_crate/ \
  -m temporal --temporal-server local --pipe-run-mode live 2>&1
```

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

**Known xfails:** Some controller execution tests fail in dry-run mode because
`StuffArtefact` objects can't serialize through Temporal's data converter. The crate
structure tests pass. These xfails will resolve once StuffArtefact serialization is fixed.

The test `test_missing_crate_fails_pipe_resolution` is a **negative test** — it intentionally
submits without a crate. The Temporal warning `Failed activation on workflow` with
`RuntimeError: No current library set` is expected.

---

## Mode 2: True 3-Process Validation

This is the real deployment test. Three separate OS processes — Temporal server, worker,
and submitter — with no shared memory. The worker has its own Python runtime, its own
`sys.modules`, its own ClassRegistry. This is the only way to catch bugs like:

- The worker can't deserialize the PipeJob because concept classes aren't registered yet
- The Kajson decoder bypasses class lookup when `__module__="builtins"`
- The Temporal data converter silently drops fields during encoding/decoding

Each command runs a pipeline through Temporal with `--graph`, which also validates that
the worker emits NDJSON trace events and the submitter assembles them into a GraphSpec
with an interactive ReactFlow HTML visualization.

### Run mode: dry-run vs live

By default, Mode 2 runs in **dry-run** mode (`--dry-run --mock-inputs`) — fast, no LLM
costs, validates serialization and crate propagation. But dry-run produces tiny mock
data, so it **cannot catch payload size issues** (e.g. large image payloads blowing up
Temporal's data converter).

Ask the user which mode they want. If they say "live", simply omit `--dry-run --mock-inputs`
from all commands below. The `pipelex run bundle` CLI has no `--pipe-run-mode` flag — live
is the default when neither `--dry-run` nor `--mock-inputs` is specified (note: pytest in
Mode 1 does accept `--pipe-run-mode live`, but the CLI does not). Live mode makes real LLM and image
generation calls — it costs money and is slower, but it's the only way to validate that
real-sized payloads (especially images) flow correctly through Temporal.

**This matters most for Tiers 4 and 5** (image generation and image flow). In dry-run,
mock images are trivially small, so payload size bugs don't surface. In live mode,
generated images are hundreds of KB to several MB — exactly the size that breaks Temporal
if activity-level storage isn't implemented.

### Step 1: Ensure Temporal server is running

Same as Mode 1 Step 1.

### Step 2: Start the worker processes

The workers should NOT have test bundles in their PIPELEXPATH — the whole point is
that bundles arrive via the LibraryCrate in the PipeJob.

**Two scoped workers (cross-process regression setup — recommended).**
Splits responsibilities so workflows and activities run in different processes:
- `router` worker registers all workflows (`WfPipeRouter`, `WfPipeRun`, …),
  `disable_all_activities = true`.
- `runner` worker registers all activities (`act_deliver`, `act_llm_*`,
  `act_assemble_graph`, `act_flush_trace_events`, …), `disable_all_workflows = true`.

This forces every activity to be picked up by a *different* Python process than the
workflow that scheduled it. The runner process never executes `WfPipeRouter`, so it
never loads the LibraryCrate and its global `ClassRegistry` stays cold for any
dynamic concept defined in the bundle.

> ⚠️ **Important — what this setup does NOT reproduce on its own.**
> Plain `pipelex run bundle` (Tiers 1–3 below) does NOT trigger the runner-side
> registry decode bug, because:
> - `WfPipeRouter` dehydrates `pipe_output` via `prepare_for_temporal()` before
>   returning, so workflow-level transit carries raw dicts (no class lookup).
> - `WfPipeRun` rehydrates back on the *router* (same process that loaded the crate).
> - Activities the runner actually executes in dry-run (`act_assemble_graph`,
>   `act_flush_trace_events`) operate on raw event records — no dynamic class needed.
> - `act_deliver` is **only scheduled when `delivery_assignment is not None`**
>   (`wf_pipe_run.py:79`), and `pipelex run bundle` does not pass one.
>
> To deterministically force a hydrated `pipe_output` across the process boundary,
> run **Tier 2b** below (mirrors the cloud / `start_pipeline` + webhook path).

```bash
tmux has-session -t temporal-worker-router 2>/dev/null && tmux kill-session -t temporal-worker-router
tmux has-session -t temporal-worker-runner 2>/dev/null && tmux kill-session -t temporal-worker-runner
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
tmux new-session -d -c "$PWD" -s temporal-worker-runner \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner'
sleep 4
tmux capture-pane -t temporal-worker-router -p -S -30
tmux capture-pane -t temporal-worker-runner -p -S -30
```

Look for `Temporal Worker started for 'temporal_task_queue'` in each session, plus
`Temporal Worker scope: 'router'` and `'runner'` respectively.

**Alternative — single full worker** (simpler, but masks distributed-execution bugs;
use only when you don't need the regression coverage):

```bash
tmux has-session -t temporal-worker 2>/dev/null && tmux kill-session -t temporal-worker
tmux new-session -d -c "$PWD" -s temporal-worker \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
sleep 4
tmux capture-pane -t temporal-worker -p -S -30
```

When using two scoped workers, replace any later capture commands like
`tmux capture-pane -t temporal-worker ...` with the appropriate session name
(`temporal-worker-router` or `temporal-worker-runner`).

### Step 3: Sequential tests — run one at a time, report after each

Do NOT clean previous results automatically — the user may want to compare runs.

**Tier 1 — Can the worker execute a simple pipe sequence?**

This sends a 2-step PipeSequence (step_one → step_two) to a worker that has never seen
these pipes. The worker must unpack the LibraryCrate, register the pipes, and execute
them in order. This is the most basic "does Temporal work at all" test.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

After this completes, tell the user: PASS/FAIL, output dir, graph file path.

**Tier 2 — Can the worker handle concepts it has never seen? (in-process hydration)**

This sends a pipeline that defines a custom concept (`Greeting` with `message` and
`language` fields) at runtime. `WfPipeRouter` must register this dynamic class
into the per-workflow registry before hydrating the WorkingMemory. If the hydration
order is wrong **on the router**, this fails with
`KajsonDecoderError: Class 'Greeting' not found`.

> Note: in dry-run with `pipelex run bundle` (no `delivery_assignment`), this tier
> only exercises hydration **on the router process**, not cross-process. It will
> pass even if the runner's registry is cold — see Tier 2b for the deterministic
> cross-process repro.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

After this completes, tell the user: PASS/FAIL, output dir, graph file path.

**Tier 2b — Cross-process registry regression (deterministic, dry-run).**

Same bundle as Tier 2, but submitted with a `DeliveryAssignment` attached. This
mirrors the cloud / `start_pipeline` + webhook path: `wf_pipe_run.py:79` then
schedules `act_deliver` on the runner with `pipe_output` carrying a hydrated
`WorkingMemory`. Temporal's data converter on the **runner process** must decode
the dynamic concept class — which is the exact path the `wf_pipe_router.py:71-80`
in-process propagation hack does NOT cover.

If the registry propagation across processes is broken, this fails every time with:

```
KajsonDecoderError: Class '<bundle>__<DynamicConcept>' not found
  in module 'builtins' or global registry
ApplicationError: Failed decoding arguments
  → temporalio/worker/_activity.py:566 (data_converter.decode_wrapper)
```

The error surfaces on the **runner** tmux session, raised by the activity worker
*before* the activity body runs.

```bash
.venv/bin/python .claude/skills/temporal-e2e-validate/scripts/repro_runner_registry_bug.py
```

To reproduce against a different bundle:

```bash
.venv/bin/python .claude/skills/temporal-e2e-validate/scripts/repro_runner_registry_bug.py \
  --bundle <path/to/bundle.mthds> --pipe <pipe_code>
```

After this completes, tell the user:
- PASS/FAIL.
- If FAIL: capture the runner log with
  `tmux capture-pane -t temporal-worker-runner -p -S -300 | tail -120`
  and quote the `KajsonDecoderError` and `ApplicationError: Failed decoding arguments`
  lines verbatim, plus the activity name (`act_deliver`).

**Tier 3 — Do parallel branches execute as separate child workflows?**

This sends a PipeParallel controller that fans out into two branches (tone analysis and
length analysis), each running as its own child workflow on the worker. The branches
execute concurrently and their results merge back. The `--graph` flag here is especially
interesting: it shows cross-worker execution with child workflow branches in the
ReactFlow visualization.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_parallel.mthds \
  --pipe temporal_parallel_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

After this completes, tell the user: PASS/FAIL, output dir, graph file path.

**Tier 4 — Can the worker handle image generation pipelines?**

**Important — split workers REQUIRED for this tier.** Run Tier 4 only when the
two scoped workers from "Step 2" above are alive (`temporal-worker-router` and
`temporal-worker-runner`). On a single full worker, image-gen routing accidents
are silently masked: every activity ends up on one process so a stray
`task_queue=` kwarg pointing at the wrong queue would still execute correctly.
Split workers are the only way to surface that class of bug as a hang or
wrong-pool execution.

**Important:** This tier only catches payload size bugs in **live mode**. In dry-run,
mock images are tiny and will pass even without activity-level storage. If the user
wants to validate image payload handling, they must run live.

This is a critical payload-size test. Image generation produces large binary data
(base64-encoded images) that must be stored at the activity level and passed as
storage URIs through Temporal — not inline in the workflow payload. If storage is
missing, this will either fail with a Temporal payload size error or trigger
`PayloadSizeWarning` in the worker logs.

The `generate_crazy_image` bundle runs a 2-step PipeSequence: an LLM imagines a
scene description, then PipeImgGen renders it as an image. This exercises the full
image generation path through Temporal, including the custom `ImagePrompt` concept
(which refines `Text`).

Dry-run:

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/crazy_image_generation.mthds \
  --pipe generate_crazy_image \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Live (real image generation — required to catch payload size bugs):

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/crazy_image_generation.mthds \
  --pipe generate_crazy_image \
  --temporal --no-logo --graph
```

After this completes, tell the user: PASS/FAIL, output dir, graph file path.
Also check worker logs for `PayloadSizeWarning`:

```bash
tmux capture-pane -t temporal-worker-router -p -S -50 | grep -i "payload\|warning\|size" || echo "No payload warnings (router)"
tmux capture-pane -t temporal-worker-runner -p -S -50 | grep -i "payload\|warning\|size" || echo "No payload warnings (runner)"
```

> For per-activity routing validation that proves image-gen lands on a
> dedicated worker pool (via `activity_queues` override), see **Step 8 —
> Routing validation battery** below.

**Tier 5 — Can generated images flow between pipes in a sequence?**

**Important — split workers REQUIRED for this tier.** Same as Tier 4 — the
mis-routing of image-gen across worker pools is only observable when router and
runner run as separate processes. On a single full worker, the bug surfaces as
"works on my machine" but breaks in production.

**Important:** Like Tier 4, this only catches real payload bugs in **live mode**.

This is the "image out → image in" test. A PipeSequence first generates an image
via PipeImgGen, then passes that image as input to a PipeLLM (vision model) that
describes it. This exercises:
- Image generation storage at the activity level
- Image content serialization through Temporal's data converter
- Image content deserialization on the worker for the next pipe step
- Vision model receiving an image reference (URI) rather than inline base64

If activity-level storage is not implemented, this will fail because the raw image
bytes exceed Temporal's payload limit, or because the worker can't deserialize the
`ImageContent` object from the previous step.

Dry-run:

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/test_image_out_in.mthds \
  --pipe image_out_in \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Live (real image generation + vision — required to catch payload size bugs):

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/test_image_out_in.mthds \
  --pipe image_out_in \
  --temporal --no-logo --graph
```

After this completes, tell the user: PASS/FAIL, output dir, graph file path.
Also check for payload warnings on both workers:

```bash
tmux capture-pane -t temporal-worker-router -p -S -50 | grep -i "payload\|warning\|size" || echo "No payload warnings (router)"
tmux capture-pane -t temporal-worker-runner -p -S -50 | grep -i "payload\|warning\|size" || echo "No payload warnings (runner)"
```

> For per-activity routing validation across the image-gen + LLM-text
> activities exercised here, see **Step 8 — Routing validation battery**
> below.

If any tier hangs for more than 30 seconds, check worker output. With the
recommended split workers (Step 2), capture both sessions; for the alternative
single full worker setup, capture `temporal-worker` instead:

```bash
# Split workers (default setup from Step 2)
tmux capture-pane -t temporal-worker-router -p -S -100
tmux capture-pane -t temporal-worker-runner -p -S -100

# Single full worker (alternative setup)
tmux capture-pane -t temporal-worker -p -S -100
```

### Step 4: Verify graph output

Check that the `--graph` flag produced ReactFlow HTML files:

```bash
ls results/*/reactflow.html 2>/dev/null
```

Tell the user where the files are and propose opening the most interesting one (the
PipeParallel graph shows cross-worker execution):

```bash
open results/temporal_parallel_sequence_output_01/reactflow.html
```

If no `reactflow.html` exists, GraphSpec assembly failed — check that tracing is enabled
in `pipelex.toml` (`[pipelex.tracing_config]` with `is_enabled = true`).

### Step 5: Concurrent isolation tests — can conflicting workflows coexist?

These are the most important safety tests. They submit two workflows simultaneously to
the same worker, where both workflows define identically-named concepts or pipes but
with different structures. If per-workflow isolation is broken, one workflow will use
the other's class definitions and either crash or silently produce wrong data.

Each pair runs with `--graph`. The graph output from backgrounded jobs goes to separate
`results/<pipe_code>_output_NN/` dirs.

**Test A — Conflicting concept names:**
Two workflows both define a concept called `Result`, but alpha's has `score` + `label`
while beta's has `value` + `confidence` + `is_valid`. If isolation fails, one workflow
will try to populate the wrong fields.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_concept_alpha.mthds \
  --pipe alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_ALPHA=$!

.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_concept_beta.mthds \
  --pipe beta_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_BETA=$!

wait $PID_ALPHA && echo "Alpha: PASS" || echo "Alpha: FAIL"
wait $PID_BETA && echo "Beta: PASS" || echo "Beta: FAIL"
```

After this, tell the user both results.

**Test B — Conflicting pipe names:**
Two workflows both define a pipe called `shared_step` but with different prompts.
Does each workflow execute its own version?

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_pipe_alpha.mthds \
  --pipe pipe_alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_ALPHA=$!

.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_pipe_beta.mthds \
  --pipe pipe_beta_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_BETA=$!

wait $PID_ALPHA && echo "Alpha: PASS" || echo "Alpha: FAIL"
wait $PID_BETA && echo "Beta: PASS" || echo "Beta: FAIL"
```

After this, tell the user both results.

**Test C — Worst case: multiple conflicting concepts at high concurrency:**
Two workflows define both `Profile` AND `Summary` with incompatible field structures.
This is the hardest isolation test — if ContextVar scoping leaks between workflows,
this is where it shows up.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/multi_concept_alpha.mthds \
  --pipe multi_alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_ALPHA=$!

.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/multi_concept_beta.mthds \
  --pipe multi_beta_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_BETA=$!

wait $PID_ALPHA && echo "Alpha: PASS" || echo "Alpha: FAIL"
wait $PID_BETA && echo "Beta: PASS" || echo "Beta: FAIL"
```

After this, tell the user both results.

### Step 5b: Tier 8 — Cross-worker usage emission (writer_id fallback)

This validates that `UsageReportEvent`s emitted from inference activities running on
the runner process land in the same NDJSON partition as the router-side trace events,
stamped with a runner-process `writer_id` (`act_{pid}_{uuid8}`). It's the e2e
counterpart to the Phase 4 integration test
`tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py`.

**Important — dry-run does NOT exercise this path.** In dry-run mode, `PipeLLM`
(and friends) instantiate `ContentGeneratorDry()` directly inside the workflow
body — on the router process — and never dispatch `act_llm_gen_text` to the
runner. So a vanilla `pipelex run bundle --temporal --dry-run` against
router+runner workers will emit ALL `usage_report` events with
`writer_id="primary"`, never `act_*`. To deterministically observe runner-side
fallback in dry-run, run the Phase 4 integration test, which substitutes the
inference activity with a wrapper that synthesizes a real `LLMJob` server-side:

```bash
.venv/bin/pytest -x -v \
  tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py \
  -m temporal --temporal-server local 2>&1
```

Expected: both test cases pass —
`test_runner_usage_event_lands_in_same_ndjson_dir` (lands in same dir, with an
`__w_act_*` file) and `test_no_double_emit_in_split_worker_pool` (no
double-counting between fast path and fallback).

**To observe `act_*` writer files via the CLI**, run live mode (real LLM call —
costs money) so `act_llm_gen_text` is actually dispatched to the runner:

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --no-logo --graph
```

After completion, list the trace files for the run:

```bash
RUN_ID=$(ls -t .pipelex/traces/ | head -1)
ls -la .pipelex/traces/$RUN_ID/
grep -l '"event_kind":"usage_report"' .pipelex/traces/$RUN_ID/*.ndjson
grep -hoE '"writer_id":"[^"]+"' .pipelex/traces/$RUN_ID/*.ndjson | sort -u
```

Expect:

- At least one `wf_*__w_act_{pid}_{uuid}.ndjson` file alongside the
  router-side `wf_*.ndjson` files.
- The runner-side file contains `usage_report` events with
  `writer_id` starting `act_`.
- Router-side files contain `pipe_start` / `pipe_end_success` events with
  `writer_id="primary"`.

If only `writer_id="primary"` appears, the inference activity ran in the
router process. Check `worker_config.activity_queues` (and the workflow's
own `task_queue`) so that `act_llm_gen_text` resolves to a queue the runner
listens on, and confirm both workers are running with the latest code
(restart them if they predate the Phase 2 runner-side fallback commit).

### Step 5c: Tier 9 — Object generation through Temporal cross-process

Validates that `act_llm_gen_object` and `act_llm_gen_object_list` survive a
cross-process round-trip. Every existing `library_crate/*.mthds` outputs `Text`,
so the structured-output activities never go through the real Temporal data
converter cross-process — Tier 9 closes that gap. The `make_object` /
`make_object_list` round-trip uses
`model_dump(mode="json", serialize_as_any=True)` and `model_validate(...)` on
the activity boundary; if either side regresses, nested fields silently drop
or fail to validate.

The `structured_output_sequence` bundle defines an `Invoice` concept with a
nested `Customer` concept and a `LineItem` list — at least one nested field
is required so the test exercises non-trivial JSON serialization.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/structured_output_sequence.mthds \
  --pipe generate_invoice_single \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/structured_output_sequence.mthds \
  --pipe generate_invoice_list \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

After each completes, tell the user: PASS/FAIL, output dir, graph file path.
The pytest counterpart in `tests/integration/pipelex/temporal/tracing/test_split_worker_object_gen.py`
runs the same scenario through the in-process server with split workers and
asserts the round-trip preserves nested field values exactly.

### Step 5d: Tier 11 — `make_extract_pages` two-activity cross-process

Validates the most fragile post-collapse path: the only `ContentGeneratorProtocol`
method that dispatches more than one activity. `make_extract_pages` runs
`act_extract_gen_extract_pages` then conditionally `act_render_page_views`,
attaching each rendered page to the corresponding `PageContent.page_view`. This
is also the only method whose `activity_id` uniqueness mitigation
(`f"{base_id}-pages"` and `f"{base_id}-render-page-views"`) actually matters in
production.

The test fixture workflow `WfTestContentGeneratorPdfPageViews` (registered in
`TEMPORAL_TEST_WORKFLOWS`) exercises this flow. The pytest counterpart
substitutes both activities with canonical fixtures so it runs without Azure
Document Intelligence credentials or pypdfium2 — the goal is to pin the
activity_id contract, not to re-validate the OCR backend (already covered by
`content_generation/test_tprl_content_generator_pdf_page_views.py`):

```bash
.venv/bin/pytest -x -v \
  tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py \
  -m temporal --temporal-server local 2>&1
```

After this completes, tell the user: PASS/FAIL. The test asserts via
`WorkflowHandle.fetch_history()` that exactly two `ActivityTaskScheduled`
events appear with `activity_id` ending in `-pages` and `-render-page-views`.
For manual Temporal Web UI inspection, point `temporal-worker-router` /
`temporal-worker-runner` at the same dev server and inspect the workflow's
event timeline — the two scheduled activities should be visible with their
distinct activity_ids.

---

### Step 6: StoragePayloadCodec tests — does the codec work end-to-end?

These tests validate Phase 5: large payloads are transparently offloaded to external
storage by the `StoragePayloadCodec`, keeping Temporal's event history small. The worker
and submitter both use the codec — it's wired at the data converter level.

**Important:** The codec config is managed via `pipelex_temporary_override.toml` — a
config layer that loads after `pipelex_override.toml` and takes highest priority. This
file is ephemeral and gitignored. **NEVER modify `pipelex_override.toml`** — that is
the user's personal config.

**Step 6a: Create the temporary override to enable the codec**

```bash
cat > .pipelex/pipelex_temporary_override.toml << 'EOF'
# Temporary override for E2E codec testing — delete when done
[temporal.payload_codec_config]
is_enabled = true
EOF
echo "Temporary override created"
```

This takes precedence over whatever codec setting exists in `pipelex_override.toml`.

**Step 6b: Restart the worker** (so it picks up the new config)

```bash
tmux has-session -t temporal-worker 2>/dev/null && tmux kill-session -t temporal-worker
tmux new-session -d -c "$PWD" -s temporal-worker \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
sleep 4
tmux capture-pane -t temporal-worker -p -S -30 | grep -i "payload codec\|Temporal Worker started"
```

Look for `Payload codec enabled` and `Temporal Worker started`.

**Tier 6 — Codec transparency: existing pipelines work unchanged**

Re-runs Tier 1 and Tier 2 with the codec on. If the codec is truly transparent, the
same pipelines produce the same results. The only difference: payloads above 1MB are
stored in `.pipelex/temporal-payload-store/` instead of inline in Temporal's event history.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/dynamic_concept_sequence.mthds \
  --pipe dynamic_greeting_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

After both complete, check that storage was used:

```bash
ls -la .pipelex/temporal-payload-store/ 2>/dev/null && echo "Storage files found" || echo "No storage files (payloads may be below threshold in dry-run)"
```

Tell the user: PASS/FAIL for each, and whether storage files were created. In dry-run
mode, payloads may be below the 1MB threshold, so no storage files is expected. In live
mode, larger payloads should trigger storage. Either way, the key assertion is that the
pipelines complete successfully.

**Tier 7 — Large payload stress test**

A 3-step pipeline that accumulates verbose text output across steps. Each step's
WorkingMemory carries the results of all previous steps, so the payload grows. In live
mode this produces realistic multi-KB to multi-MB payloads. In dry-run mode, mock
outputs are small but the codec path is still exercised.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/large_payload_sequence.mthds \
  --pipe large_payload_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Live (real LLM calls — produces larger payloads, better stress test):

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/large_payload_sequence.mthds \
  --pipe large_payload_sequence \
  --temporal --no-logo --graph
```

After this completes, check storage and worker logs:

```bash
ls -la .pipelex/temporal-payload-store/ 2>/dev/null | head -20
tmux capture-pane -t temporal-worker -p -S -50 | grep -i "payload\|warning\|size\|codec" || echo "No payload warnings"
```

Tell the user: PASS/FAIL, output dir, graph file path, storage file count.

**Step 6c: Remove the temporary override**

```bash
.venv/bin/python -c "from pathlib import Path; Path('.pipelex/pipelex_temporary_override.toml').unlink(missing_ok=True)"
echo "Temporary override removed"
```

Optionally restart the worker to restore the base codec config, or leave it if done.

### Step 7: Final report

List all graph files and present a summary table with results:

```bash
ls results/*/reactflow.html
```

| Test | What it proved | Status | Graph | Payload warnings |
|------|---------------|--------|-------|-----------------|
| Tier 1: Sequence | Worker can unpack crate and run a pipe sequence | PASS/FAIL | path | — |
| Tier 2: Hydration | Worker handles dynamic concepts it has never seen | PASS/FAIL | path | — |
| Tier 2b: Cross-process registry | `act_deliver` decodes hydrated `pipe_output` on runner (forced via `delivery_assignment`) | PASS/FAIL | — | — |
| Tier 3: Parallel | Branches execute as concurrent child workflows | PASS/FAIL | path | — |
| Tier 4: ImgGen | Image generation pipeline works through Temporal | PASS/FAIL | path | yes/no |
| Tier 5: Image flow | Generated image flows as input to next pipe step | PASS/FAIL | path | yes/no |
| Tier 6: Codec transparency | Existing pipelines work unchanged with codec enabled | PASS/FAIL | path | — |
| Tier 7: Large payload | Multi-step pipeline with codec stress test | PASS/FAIL | path | — |
| Tier 8: Cross-worker usage | Runner-side `UsageReportEvent` lands in same NDJSON dir with `act_*` writer_id (live mode or integration test) | PASS/FAIL | — | — |
| Tier 9: Object gen cross-process | `act_llm_gen_object` / `act_llm_gen_object_list` survive the JSON round-trip with nested fields intact | PASS/FAIL | path | — |
| Tier 10a: Multi-activity routing | `activity_queues.default` routes both `act_llm_gen_text` and `act_img_gen_images` to their dedicated worker pools; default runner sees 0 hits for either | PASS/FAIL/SKIPPED | — | — |
| Tier 10b: Per-handle routing | `activity_queues.by_handle` overrides the activity default per model handle — two distinct handles in one workflow land on two distinct workers | PASS/FAIL/SKIPPED | path | — |
| Tier 10c: Two activities, one route | `act_extract_gen_extract_pages` + `act_render_page_views` (no routing key) both land on a shared dedicated queue via Azure Doc Intel through Pipelex Gateway | PASS/FAIL | — | — |
| Tier 11: Extract two-activity | `act_extract_gen_extract_pages` + `act_render_page_views` dispatched cross-process with distinct activity_ids | PASS/FAIL | — | — |
| Scenario A: v2 multi-class routing | Specialized scopes + per-class runners cover LLM/img-gen/extract without cross-class leakage | PASS/FAIL/SKIPPED | — | — |
| Scenario B: per-queue timeout | `queue_options[X].start_to_close_timeout` overrides the worker_config baseline and flows into `ActivityTaskScheduled.start_to_close_timeout` | PASS/FAIL/SKIPPED | — | — |
| Scenario C: per-handle override | `handle_options[<handle>].start_to_close_timeout` wins over per-queue value for that one handle | PASS/FAIL/SKIPPED | — | — |
| Scenario D: queue rate limit | `queue_options[X].max_task_queue_activities_per_second` throttles dispatch — burst of N at rate R produces non-zero schedule_to_start latency on the tail | PASS/FAIL/SKIPPED | — | — |
| Scenario E: missing-worker timeout | A queue referenced by routing but polled by no worker produces a bounded `schedule_to_start` timeout, not a hang | PASS/FAIL/SKIPPED | — | — |
| Scenario F: CLI typo | `--task-queue typo_q` fails fast with `WorkerTaskQueueUnknownError` and a "Did you mean?" suggestion | PASS/FAIL | — | — |
| Concept isolation (alpha) | Conflicting `Result` concepts don't cross-contaminate | PASS/FAIL | path | — |
| Concept isolation (beta) | (same test, other side) | PASS/FAIL | path | — |
| Pipe isolation (alpha) | Conflicting `shared_step` pipes use correct version | PASS/FAIL | path | — |
| Pipe isolation (beta) | (same test, other side) | PASS/FAIL | path | — |
| Multi-concept (alpha) | Two overlapping concepts with incompatible structures | PASS/FAIL | path | — |
| Multi-concept (beta) | (same test, other side) | PASS/FAIL | path | — |

After reporting, propose opening the PipeParallel graph (most interesting cross-worker view):

```bash
open results/temporal_parallel_sequence_output_01/reactflow.html
```

If any concurrent tests fail, capture worker output for diagnosis (split workers
from Step 2 are the default — fall back to `temporal-worker` only if you used the
single full worker setup):

```bash
tmux capture-pane -t temporal-worker-router -p -S -200
tmux capture-pane -t temporal-worker-runner -p -S -200
```

---

### Step 8: Routing validation battery — does `activity_queues` actually isolate workers?

This step validates the v1 per-activity, per-handle routing (PR #879) end-to-end
against a real Temporal server. It is **opt-in** — Tiers 1–11 above all run with
the default empty `activity_queues`, where every activity lands on
`worker_config.default_task_queue` and either of the split workers picks it up. Step 8
proves the routing feature works as advertised when operators actually configure
it: each activity (and, in Tier 10b, each model handle) lands on its dedicated
worker pool, never on the fallback runner.

Step 8 is **live-only**. The routing decision happens in the workflow regardless
of dry/live, but the only way to prove a routed activity wasn't picked up by the
wrong worker is to actually dispatch it and watch where it executes. Dry-run
short-circuits LLM calls inside the workflow process (`ContentGeneratorDry`),
so no `act_*` ever gets scheduled and the routing assertion is meaningless.

**Step 8.0 — Preflight + setup**

Verify base split workers from Step 2 are still alive (router + runner). If not,
go back and start them.

Write the routing override:

```bash
cat > .pipelex/pipelex_temporary_override.toml << 'EOF'
[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "q_inference"
by_handle = { "claude-4.6-sonnet" = "q_handle_a", "gemini-flash-latest" = "q_handle_b" }

[temporal.worker_config.activity_queues.act_img_gen_images]
default = "q_image_gen"

[temporal.worker_config.activity_queues.act_extract_gen_extract_pages]
default = "q_extract"

[temporal.worker_config.activity_queues.act_render_page_views]
default = "q_extract"
EOF
```

The override needs to be visible to the **router** process (where `resolve_queue`
runs inside the workflow). The dedicated activity workers don't read this config
— they just listen on the queue named in their `--task-queue` flag. Restart the
router so it reloads config:

```bash
tmux kill-session -t temporal-worker-router
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
sleep 4
tmux capture-pane -t temporal-worker-router -p -S -30 | grep "Temporal Worker started"
```

Spawn the five dedicated activity workers, one per named queue:

```bash
for q in q_inference q_handle_a q_handle_b q_image_gen q_extract; do
  session="temporal-worker-${q//_/-}"
  tmux has-session -t "$session" 2>/dev/null && tmux kill-session -t "$session"
  tmux new-session -d -c "$PWD" -s "$session" \
    ".venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner --task-queue $q"
done
sleep 5
for q in q_inference q_handle_a q_handle_b q_image_gen q_extract; do
  session="temporal-worker-${q//_/-}"
  echo "=== $session ==="
  tmux capture-pane -t "$session" -p -S -20 | grep -B 1 -A 1 "started for"
done
```

Each session should report `Temporal Worker started for '<queue>'`. If any
worker failed to start, stop and diagnose before running the sub-tiers.

**Tier 10a — Multi-activity isolation (live)**

Runs an image-generation pipeline that dispatches `act_llm_gen_text` (handle
resolves to `gpt-4o-mini` via `@default-small` — not in `by_handle`, falls through
to activity default `q_inference`) AND `act_img_gen_images` (default → `q_image_gen`).
Both activities must land on their dedicated workers; the inference runner from
Step 2 must see 0 hits for either.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/crazy_image_generation.mthds \
  --pipe generate_crazy_image \
  --temporal --no-logo --graph
```

After completion:

```bash
INF=$(tmux capture-pane -t temporal-worker-q-inference -p -S -500 | grep -c "act_llm_gen_text")
IMG=$(tmux capture-pane -t temporal-worker-q-image-gen -p -S -500 | grep -c "act_img_gen_images")
INF_IMG=$(tmux capture-pane -t temporal-worker-q-inference -p -S -500 | grep -c "act_img_gen_images")
IMG_LLM=$(tmux capture-pane -t temporal-worker-q-image-gen -p -S -500 | grep -c "act_llm_gen_text")
RUN_LLM=$(tmux capture-pane -t temporal-worker-runner -p -S -500 | grep -c "act_llm_gen_text")
RUN_IMG=$(tmux capture-pane -t temporal-worker-runner -p -S -500 | grep -c "act_img_gen_images")
echo "q_inference   llm=$INF        img=$INF_IMG (want llm≥1, img=0)"
echo "q_image_gen   llm=$IMG_LLM    img=$IMG     (want llm=0,  img≥1)"
echo "runner        llm=$RUN_LLM    img=$RUN_IMG (want llm=0,  img=0)"
if [ "$INF" -ge 1 ] && [ "$IMG" -ge 1 ] && [ "$INF_IMG" -eq 0 ] && [ "$IMG_LLM" -eq 0 ] && [ "$RUN_LLM" -eq 0 ] && [ "$RUN_IMG" -eq 0 ]; then
  echo "Tier 10a PASS: multi-activity isolation verified"
else
  echo "Tier 10a FAIL — see hit table above"
fi
```

**Tier 10b — Per-handle routing (live)**

Runs `per_handle_routing.mthds`, a 2-step PipeSequence that dispatches `act_llm_gen_text`
twice — step 1 with `model = "claude-4.6-sonnet"`, step 2 with `model = "gemini-flash-latest"`.
The override maps each handle to its own queue via `by_handle`. After execution,
each per-handle worker should show exactly 1 hit for `act_llm_gen_text`, and
`q_inference` (the activity default) should see 0 — proving the per-handle layer
wins over the activity default.

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/per_handle_routing.mthds \
  --pipe per_handle_routing_sequence \
  --temporal --no-logo --graph
```

After completion:

```bash
HA=$(tmux capture-pane -t temporal-worker-q-handle-a -p -S -500 | grep -c "act_llm_gen_text")
HB=$(tmux capture-pane -t temporal-worker-q-handle-b -p -S -500 | grep -c "act_llm_gen_text")
INF=$(tmux capture-pane -t temporal-worker-q-inference -p -S -500 | grep -c "act_llm_gen_text")
RUN=$(tmux capture-pane -t temporal-worker-runner -p -S -500 | grep -c "act_llm_gen_text")
echo "q_handle_a (claude)  hits=$HA  (want ≥1)"
echo "q_handle_b (gemini)  hits=$HB  (want ≥1)"
echo "q_inference          hits=$INF (want delta=0 from Tier 10a baseline — by_handle wins)"
echo "runner               hits=$RUN (want delta=0 from Tier 10a baseline)"
if [ "$HA" -ge 1 ] && [ "$HB" -ge 1 ]; then
  echo "Tier 10b PASS: per-handle routing verified (both handles landed on their dedicated workers)"
else
  echo "Tier 10b FAIL — see hit table above"
fi
```

Note: `q_inference` and `runner` hit counts include Tier 10a's `act_llm_gen_text`
dispatch (1 from Tier 10a's `@default-small` → `gpt-4o-mini` call landing on
`q_inference`). The Tier 10b assertion is that neither counter incremented after
this run — i.e. both Tier 10b dispatches landed on their per-handle workers.
If you ran Step 8 from a fresh session restart, `q_inference` should be exactly
1 (from Tier 10a) and `runner` should be 0.

**Tier 10c — Two activities, one route (live)**

**Credentials note.** This repo's `.env` provides `PIPELEX_GATEWAY_API_KEY`
and `PIPELEX_INFERENCE_API_KEY` — the Pipelex Gateway proxies extract
backends (including Azure Document Intelligence) without needing direct
`AZURE_DOCUMENT_INTELLIGENCE_*` env vars. Use the
`azure-document-intelligence` handle directly; do **NOT** substitute
`mistral-ocr` or `deepseek-ocr` even when those handles seem available.
User preference: extract = Azure Doc Intel via the gateway, period. (The
`mistral-ocr` handle defined in `mistral.toml` is not auto-registered in
the deck on this setup — `is_model_handle_defined` returns False — so
trying it produces `Extract choice '...mistral-ocr...' was not found in the
model deck`. Skip that path.)

The existing bundle at
`tests/integration/pipelex/temporal/library_crate/pdf_extract_page_views.mthds`
already references `@default-extract-document` (→ `azure-document-intelligence`)
and sets `page_views = true`, exercising both activities. There is no
matching inputs JSON for the CLI run — write one at `/tmp/pdf_extract_inputs.json`
pointing at any `tests/data/documents/*.pdf` (e.g. `Job-Offer.pdf`):

```bash
cat > /tmp/pdf_extract_inputs.json << EOF
{
  "source_pdf": {
    "concept": "native.Document",
    "content": {
      "url": "$PWD/tests/data/documents/Job-Offer.pdf"
    }
  }
}
EOF

.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/pdf_extract_page_views.mthds \
  --pipe pdf_extract_with_page_views \
  --inputs /tmp/pdf_extract_inputs.json \
  --temporal --no-logo --graph
```

After completion:

```bash
EXTR=$(tmux capture-pane -t temporal-worker-q-extract -p -S -500 | grep -c "act_extract_gen_extract_pages")
RNDR=$(tmux capture-pane -t temporal-worker-q-extract -p -S -500 | grep -c "act_render_page_views")
RUN_EXTR=$(tmux capture-pane -t temporal-worker-runner -p -S -500 | grep -c "act_extract_gen_extract_pages")
RUN_RNDR=$(tmux capture-pane -t temporal-worker-runner -p -S -500 | grep -c "act_render_page_views")
echo "q_extract: extract=$EXTR (want ≥1)  render=$RNDR (want ≥1)"
echo "runner:    extract=$RUN_EXTR        render=$RUN_RNDR (want both 0)"
if [ "$EXTR" -ge 1 ] && [ "$RNDR" -ge 1 ] && [ "$RUN_EXTR" -eq 0 ] && [ "$RUN_RNDR" -eq 0 ]; then
  echo "Tier 10c PASS: both extract activities routed to q_extract (activity-default fallback for routing_key=None works)"
else
  echo "Tier 10c FAIL — see hit table above"
fi
```

If the pipeline ever errors with `Extract choice '...' was not found in the
model deck`, the deck is not loading Azure Doc Intel — fix the deck before
falling back to a different handle; do not substitute another OCR backend.

**Step 8.d — Teardown**

Restore the default empty `activity_queues` and kill the dedicated workers:

```bash
rm -f .pipelex/pipelex_temporary_override.toml
for q in q_inference q_handle_a q_handle_b q_image_gen q_extract; do
  tmux kill-session -t "temporal-worker-${q//_/-}" 2>/dev/null
done
# Restart the router so it reverts to empty activity_queues
tmux kill-session -t temporal-worker-router
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
sleep 4
tmux capture-pane -t temporal-worker-router -p -S -10 | grep "Temporal Worker started"
```

Optionally re-run Tier 1 (default routing) to confirm the baseline is restored.

---

### Step 9: Queue options + worker-runtime profiles battery (v2)

This step validates the v2 surfaces shipped on top of v1 routing:

- **Per-queue submitter options** (`[temporal.queue_options.<q>]`) — timeouts and retry policy attach to the queue, not the activity.
- **Per-handle option overrides** (`activity_queues.*.handle_options.<handle>`) — a single handle on a queue can override the queue baseline.
- **Cluster-wide queue rate limit** (`queue_options[q].max_task_queue_activities_per_second`).
- **Named worker-runtime profiles** (`[temporal.worker_runtime_profiles.profiles.<name>]`) — concurrency slots, pollers, and rate-limit knobs become per-worker config selected via `--profile`.
- **Startup validation** — warn on unknown routing queues; fail with "did you mean?" on unknown `--task-queue`.

All scenarios A-D below are **live-only** for the same reason as Step 8: dry-run short-circuits inference inside the workflow process, so `act_*` activities never get scheduled and the routing/timeout/rate-limit assertions are meaningless.

**Step 9.0 — Preflight + setup**

Build a temporary override exercising the new schema. Notice the named `worker_runtime_profiles` and `queue_options` blocks layered on top of v1 `activity_queues`:

```bash
cat > .pipelex/pipelex_temporary_override.toml << 'EOF'
# v1 routing — drives which queue each activity lands on.
[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "q_llm"
by_handle = { "claude-4.6-sonnet" = "q_llm_anthropic" }

[temporal.worker_config.activity_queues.act_img_gen_images]
default = "q_imggen"

[temporal.worker_config.activity_queues.act_extract_gen_extract_pages]
default = "q_extract"

[temporal.worker_config.activity_queues.act_render_page_views]
default = "q_extract"

# Scenario B — per-queue timeout. q_slow has a generous start_to_close; the baseline is tight.
[temporal.worker_config]
default_activity_start_to_close_timeout = "0:00:30"   # baseline tight on purpose

[temporal.queue_options.q_llm]
start_to_close_timeout = "0:05:00"

[temporal.queue_options.q_llm_anthropic]
start_to_close_timeout = "0:05:00"

[temporal.queue_options.q_capped]
max_task_queue_activities_per_second = 2              # scenario D — cluster rate cap

# Scenario C — per-handle override on top of per-queue.
[temporal.worker_config.activity_queues.act_llm_gen_text.handle_options."claude-opus-4-7-1m"]
start_to_close_timeout = "0:25:00"

# Scenario A also exercises differently-shaped worker profiles per pool.
[temporal.worker_runtime_profiles]
default_profile = "default"

[temporal.worker_runtime_profiles.profiles.llm-throughput]
tuning_mode = "explicit"
max_cached_workflows = 10000
max_concurrent_workflow_tasks = 1000
max_concurrent_activities = 50
max_concurrent_local_activities = 1000
max_concurrent_workflow_task_polls = 100
max_concurrent_activity_task_polls = 20
max_activities_per_second = 60
sticky_queue_schedule_to_start_timeout = "0:30:00"
max_heartbeat_throttle_interval = "1:00:00"
default_heartbeat_throttle_interval = "1:00:00"
graceful_shutdown_timeout = "0:30:00"

[temporal.worker_runtime_profiles.profiles.img-gen-tight]
tuning_mode = "explicit"
max_cached_workflows = 10000
max_concurrent_workflow_tasks = 1000
max_concurrent_activities = 2                          # small parallelism, large payloads
max_concurrent_local_activities = 1000
max_concurrent_workflow_task_polls = 100
max_concurrent_activity_task_polls = 100
max_activities_per_second = 2
sticky_queue_schedule_to_start_timeout = "0:30:00"
max_heartbeat_throttle_interval = "1:00:00"
default_heartbeat_throttle_interval = "1:00:00"
graceful_shutdown_timeout = "0:10:00"
EOF
```

Restart the router (only the router reads `activity_queues` / `queue_options` at dispatch time):

```bash
tmux kill-session -t temporal-worker-router 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
sleep 4
tmux capture-pane -t temporal-worker-router -p -S -30 | grep "Temporal Worker started"
```

Spawn one specialized runner per queue, each with a profile shaped for its workload. Note the use of the new `runner-llm` / `runner-img-gen` / `runner-extract` scopes shipped in Phase 5:

```bash
tmux has-session -t temporal-worker-q-llm 2>/dev/null && tmux kill-session -t temporal-worker-q-llm
tmux new-session -d -c "$PWD" -s temporal-worker-q-llm \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner-llm --profile llm-throughput --task-queue q_llm'

tmux has-session -t temporal-worker-q-llm-anthropic 2>/dev/null && tmux kill-session -t temporal-worker-q-llm-anthropic
tmux new-session -d -c "$PWD" -s temporal-worker-q-llm-anthropic \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner-llm --profile llm-throughput --task-queue q_llm_anthropic'

tmux has-session -t temporal-worker-q-imggen 2>/dev/null && tmux kill-session -t temporal-worker-q-imggen
tmux new-session -d -c "$PWD" -s temporal-worker-q-imggen \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner-img-gen --profile img-gen-tight --task-queue q_imggen'

tmux has-session -t temporal-worker-q-extract 2>/dev/null && tmux kill-session -t temporal-worker-q-extract
tmux new-session -d -c "$PWD" -s temporal-worker-q-extract \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner-extract --task-queue q_extract'

sleep 5
for q in q-llm q-llm-anthropic q-imggen q-extract; do
  echo "=== temporal-worker-$q ==="
  tmux capture-pane -t "temporal-worker-$q" -p -S -20 | grep -E "started for|profile=|scope=" | head -3
done
```

Each line should report `profile='<name>' scope='<name>' task_queue='<q>'`. Profile selection should be visible in the worker startup log (introduced by the Phase 3 logging).

**Scenario A — Multi-class routing with specialized scopes (live)**

The v2 counterpart of Tier 10a, but using the specialized `runner-llm` / `runner-img-gen` / `runner-extract` scopes instead of bare `runner`. Each worker only registers its own activity class, so a stray routing decision lands on the wrong queue and the activity never executes (instead of being silently picked up by a generalist runner).

Submit a pipeline that fires at least one activity of each class:

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/crazy_image_generation.mthds \
  --pipe generate_crazy_image \
  --temporal --no-logo --graph
```

After completion:

```bash
LLM_HITS=$(tmux capture-pane -t temporal-worker-q-llm -p -S -500 | grep -c "act_llm_gen_text")
IMG_HITS=$(tmux capture-pane -t temporal-worker-q-imggen -p -S -500 | grep -c "act_img_gen_images")
LLM_IMG_CROSS=$(tmux capture-pane -t temporal-worker-q-llm -p -S -500 | grep -c "act_img_gen_images")
IMG_LLM_CROSS=$(tmux capture-pane -t temporal-worker-q-imggen -p -S -500 | grep -c "act_llm_gen_text")
echo "q_llm     llm=$LLM_HITS    cross-class img=$LLM_IMG_CROSS (want llm≥1, img=0)"
echo "q_imggen  img=$IMG_HITS    cross-class llm=$IMG_LLM_CROSS (want img≥1, llm=0)"
if [ "$LLM_HITS" -ge 1 ] && [ "$IMG_HITS" -ge 1 ] && [ "$LLM_IMG_CROSS" -eq 0 ] && [ "$IMG_LLM_CROSS" -eq 0 ]; then
  echo "Scenario A PASS"
else
  echo "Scenario A FAIL — see hit table"
fi
```

**Scenario B — Per-queue timeout applied (live)**

The override sets `default_activity_start_to_close_timeout = "0:00:30"` (baseline tight) and `queue_options.q_llm.start_to_close_timeout = "0:05:00"` (generous). An LLM activity routed to `q_llm` should use 5min, not 30s. Read it back from workflow history:

```bash
.venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --no-logo --graph
```

After completion, find the latest workflow run in the dev UI (http://localhost:8233) and inspect any `ActivityTaskScheduled` event for `act_llm_gen_text`. Its `start_to_close_timeout` field should show `300s` (= 5min), not `30s`. To check programmatically, use the Temporal CLI:

```bash
RUN_ID=$(temporal workflow list --limit 1 --output json | jq -r '.[0].execution.run_id')
WF_ID=$(temporal workflow list --limit 1 --output json | jq -r '.[0].execution.workflow_id')
temporal workflow show --workflow-id "$WF_ID" --run-id "$RUN_ID" --output json \
  | jq '.events[] | select(.activityTaskScheduledEventAttributes.activityType.name == "act_llm_gen_text") | .activityTaskScheduledEventAttributes.startToCloseTimeout'
```

Expected output: `"300s"`. Anything else (especially `"30s"`) means the resolver didn't pick up the per-queue overlay — Scenario B FAIL.

**Scenario C — Per-handle override wins over per-queue (live)**

Two LLM calls routed to `q_llm_anthropic`: one with a regular Anthropic handle (uses queue baseline `0:05:00`), one with `claude-opus-4-7-1m` (the handle_options entry overrides to `0:25:00`). The reusable `per_handle_routing.mthds` bundle from Step 8 can serve here, but with a manual pipe definition where step 2 uses model `"claude-opus-4-7-1m"` — adapt or write a new bundle. For now, validate via the per-queue value flowing as in Scenario B, plus inspect the `start_to_close_timeout` per scheduled activity in history: one should be `300s`, one should be `1500s`.

The full pytest integration sibling for this scenario already exists at:
`tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::test_queue_options_start_to_close_timeout_flows_to_dispatch`.
Run that to validate the resolver layer without spinning up the live CLI:

```bash
.venv/bin/pytest -xvs tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::TestSplitWorkerExtractPages::test_queue_options_start_to_close_timeout_flows_to_dispatch \
  -m temporal --temporal-server local
```

PASS = per-queue timeout flows through the resolver into the actual dispatch. The handle-options layer is covered by `tests/unit/pipelex/temporal/test_resolve_dispatch.py::test_handle_options_override_queue`.

**Scenario D — Queue-level rate limit observed (live)**

`queue_options.q_capped.max_task_queue_activities_per_second = 2`. Submit a burst (workflow with ≥10 activity dispatches to `q_capped`). The server enforces 2 RPS, so the tail activities should show non-zero `scheduledToStartTimeout` latency (waited in the queue before being picked up).

There is no canned pipeline for this — write a temporary bundle that fans out, e.g. a PipeBatch on 10 items each calling `act_llm_gen_text` routed to `q_capped`. After completion:

```bash
temporal workflow show --workflow-id "<wf_id>" --run-id "<run_id>" --output json \
  | jq '[.events[] | select(.activityTaskStartedEventAttributes != null)] | length as $started
        | [.events[] | select(.activityTaskScheduledEventAttributes != null and
                                .activityTaskScheduledEventAttributes.taskQueue.name == "q_capped") |
           .eventTime] | sort | map(fromdateiso8601) |
          {first: .[0], last: .[-1], span_seconds: (.[-1] - .[0]), total: length}'
```

PASS criteria (per TODOS.md): ordering of dispatches is preserved AND `span_seconds` is non-zero for 10 activities at 2 RPS. Don't pin exact timing — the server's rate-limit precision is per-second, not millisecond.

**Scenario E — Missing-worker negative (live, bounded)**

Route an activity to a queue nothing polls. Override:

```bash
cat >> .pipelex/pipelex_temporary_override.toml << 'EOF'

[temporal.worker_config.activity_queues.act_jinja2_gen_text]
default = "q_orphan"
EOF
```

Restart the router (re-read the override), then submit a pipeline that fires `act_jinja2_gen_text`. With Phase 4's strict CLI validation, the worker process would refuse to start on `--task-queue q_orphan` if you tried — but a routing-only orphan queue (referenced in `activity_queues`) is fine until dispatch.

After submission, the workflow's first `act_jinja2_gen_text` invocation will time out on `schedule_to_start`. Bound the wait by setting `queue_options.q_orphan.schedule_to_start_timeout = "0:00:30"`. Expected: the workflow fails with a clear `schedule_to_start` timeout, not a hang.

```bash
.venv/bin/pipelex run bundle \
  <some_bundle_using_jinja2>.mthds \
  --pipe <pipe_using_templating> \
  --temporal --no-logo
```

Expected: non-zero exit within ~35s with `ScheduleToStartTimeout` in the error chain. PASS = bounded timeout, clear error. FAIL = hangs > 60s or unclear error.

**Scenario F — CLI startup typo (no live submission)**

`pipelex worker --task-queue typo_q` (where `typo_q` isn't in `queue_options`, `activity_queues`, or `default_task_queue`) must exit non-zero with the Phase 4 "did you mean?" suggestion. No tmux session needed — run inline:

```bash
.venv/bin/python -m pipelex.temporal.worker_cli --task-queue temporal_task_queu 2>&1 | tail -20
```

PASS = process exits with non-zero status and the error contains:

```
WorkerTaskQueueUnknownError: --task-queue 'temporal_task_queu' is not referenced by any routing or options entry.
Known queues: [...]. Did you mean 'temporal_task_queue'?
```

FAIL = process starts up, hangs, or errors with a different message.

Sanity-check that a known queue passes:

```bash
.venv/bin/python -m pipelex.temporal.worker_cli --task-queue q_llm --is-unit-testing 2>&1 | head -10
```

Should start up (proceed past the validator without raising).

**Step 9.t — Teardown**

```bash
rm -f .pipelex/pipelex_temporary_override.toml
for q in q-llm q-llm-anthropic q-imggen q-extract; do
  tmux kill-session -t "temporal-worker-$q" 2>/dev/null
done
tmux kill-session -t temporal-worker-router 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
sleep 4
tmux capture-pane -t temporal-worker-router -p -S -10 | grep "Temporal Worker started"
```

---

## Cleanup

Propose these to the user — do NOT run them automatically:

- Kill tmux sessions: `tmux kill-session -t temporal-worker-router` / `tmux kill-session -t temporal-worker-runner` (or `tmux kill-session -t temporal-worker` if you used the single full worker) / `tmux kill-session -t temporal-server`
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

**Image payload bundles** — in `tests/integration/pipelex/pipes/pipelines/`:

| Bundle | What it tests | Main pipe |
|--------|--------------|-----------|
| `crazy_image_generation.mthds` | Image generation pipeline — LLM imagines scene + PipeImgGen renders it, custom ImagePrompt concept | `generate_crazy_image` |
| `test_image_out_in.mthds` | Image flow — PipeImgGen generates image, then PipeLLM (vision) describes it | `image_out_in` |
