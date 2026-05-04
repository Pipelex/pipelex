---
name: temporal-e2e-validate
description: >
  Full end-to-end validation of Temporal distributed execution (Phases 2-5).
  Two modes: (1) pytest against a real Temporal server for detailed assertions on
  all test cases, and (2) true 3-process setup (server + separate worker process
  + submitter) that validates the actual deployment topology including cross-process
  serialization, LibraryCrate propagation, deferred hydration, concurrent
  isolation, image payload storage, and cross-worker graph tracing with GraphSpec
  assembly. Includes image generation and image flow tests that verify large binary
  payloads are stored at the activity level (not passed inline through Temporal).
  Use when the user says "validate temporal", "e2e temporal",
  "temporal regression", "temporal validation", "3-process test", "full temporal
  test", "validate phases", "image temporal", or wants comprehensive verification
  that distributed execution works end-to-end. Also use proactively after changes
  to LibraryCrate, deferred hydration, ClassRegistry scoping, graph tracing,
  image generation activities, content storage, or Temporal workflow code.
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
  Check worker output: tmux capture-pane -t temporal-worker -p -S -200
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
tmux capture-pane -t temporal-worker -p -S -50 | grep -i "payload\|warning\|size" || echo "No payload warnings"
```

**Tier 5 — Can generated images flow between pipes in a sequence?**

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
Also check for payload warnings:

```bash
tmux capture-pane -t temporal-worker -p -S -50 | grep -i "payload\|warning\|size" || echo "No payload warnings"
```

If any tier hangs for more than 30 seconds, check worker output:

```bash
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
router process — check `worker_config.inference_task_queue` and confirm both
workers are running with the latest code (restart them if they predate the
Phase 2 runner-side fallback commit).

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

If any concurrent tests fail, capture worker output for diagnosis:

```bash
tmux capture-pane -t temporal-worker -p -S -200
```

---

## Cleanup

Propose these to the user — do NOT run them automatically:

- Kill tmux sessions: `tmux kill-session -t temporal-worker` / `tmux kill-session -t temporal-server`
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
| Submitter hangs indefinitely | The worker crashed during deserialization — check `tmux capture-pane -t temporal-worker -p -S -200` |
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
