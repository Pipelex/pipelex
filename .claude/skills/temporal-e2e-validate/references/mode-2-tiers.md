# Temporal E2E — Mode 2 tiers: Steps 3–7

> Reference file for the **temporal-e2e-validate** skill — Mode 2, Steps 3–7.
> **Run `mode-2-setup.md` first** (Steps 1–2: Temporal server + worker processes) — every tier here assumes the server and worker(s) are already up.
> The **Timeouts policy** and the **surface-results-immediately** rule in `SKILL.md` apply to every command here.
> Sibling reference files: `routing-battery.md` (Step 8 — v1 routing), `queue-options-battery.md` (Step 9 — v2 queue options / worker-runtime profiles).

## Contents

- **Step 3** — Sequential tests: Tier 1 (sequence), Tier 2 (hydration), Tier 2b (cross-process registry), Tier 2c (validate sweep stays in-process), Tier 2d (dry-run+validate as one in-memory activity), Tier 3 (parallel), Tier 4 (image generation), Tier 5 (image flow)
- **Step 4** — Verify graph output
- **Step 5** — Concurrent isolation tests (concept / pipe / multi-concept)
- **Step 5b** — Tier 8: cross-worker usage emission; Tier 8b: cross-worker cost report assembly (`--mock-inference`, free)
- **Step 5c** — Tier 9: object generation cross-process
- **Step 5d** — Tier 11: `make_extract_pages` two-activity cross-process
- **Step 5e** — Tier 12: deeply-nested controller stack (CV batch screening)
- **Step 5f** — Tiers 13–16: error propagation across the activity → workflow → submitter boundary (LLM, extract, image-gen, and batched child-workflow failures)
- **Step 6** — StoragePayloadCodec tests: Tier 6 (codec transparency), Tier 7 (large payload)
- **Step 7** — Final report (master results table)

---

### Step 3: Sequential tests — run one at a time, report after each

Do NOT clean previous results automatically — the user may want to compare runs.

**Tier 1 — Can the worker execute a simple pipe sequence?**

This sends a 2-step PipeSequence (step_one → step_two) to a worker that has never seen
these pipes. The worker must unpack the LibraryCrate, register the pipes, and execute
them in order. This is the most basic "does Temporal work at all" test.

```bash
timeout 120 .venv/bin/pipelex run bundle \
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
timeout 120 .venv/bin/pipelex run bundle \
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
timeout 120 .venv/bin/python .claude/skills/temporal-e2e-validate/scripts/repro_runner_registry_bug.py
```

To reproduce against a different bundle:

```bash
timeout 120 .venv/bin/python .claude/skills/temporal-e2e-validate/scripts/repro_runner_registry_bug.py \
  --bundle <path/to/bundle.mthds> --pipe <pipe_code>
```

After this completes, tell the user:
- PASS/FAIL.
- If FAIL: capture the runner log with
  `tmux capture-pane -t temporal-worker-runner -p -S -300 | tail -120`
  and quote the `KajsonDecoderError` and `ApplicationError: Failed decoding arguments`
  lines verbatim, plus the activity name (`act_deliver`).

**Tier 2c — Validate sweep stays in-process under a Temporal-enabled boot (submitter-side leak guard).**

This is **not** a `run` — it's a `validate`. It guards the production bug where the `/validate`
dry-run sweep leaked nested controller sub-pipes to Temporal: a standalone `PipeBatch` swept directly
fans out over a mock list and dispatches each branch through `get_pipe_router()`, which under a
Temporal-enabled hub is the `TemporalPipeRouter`. Those concurrent same-id top-level dispatches raised
`WorkflowAlreadyStartedError` → the API returned **HTTP 422** with `Failed to execute workflow
WfPipeRouter`. The fix scopes an in-process router for the whole sweep; the contract here is that
validation **never dispatches to Temporal**, even when booted Temporal-enabled.

The `--temporal` flag (parity with `pipelex run`) flips the boot's hub default to the Temporal router
with no `pipelex_temporary_override.toml` juggling. With the fix, the sweep still stays in-process —
which is exactly what this asserts. `temporal_batch.mthds` declares a standalone `type = "PipeBatch"`
pipe (`batch_temporal_describe_topics`), so its sweep fans out — the exact shape that 422'd.

```bash
# Server + worker up (Mode 2). The boot connects Temporal-enabled; with the fix the sweep stays
# in-process, so the worker must receive NO workflow for this validate run.
# Capture pipelex's OWN exit code (load-bearing for GREEN/RED). Don't pipe the command into
# `tail` and read `$?` — that's tail's exit; and `${PIPESTATUS[0]}` is bash-only (blank in zsh).
# Redirect to a file, read `$?` with no pipe in between, then tail the log. Works in bash AND zsh.
timeout 120 .venv/bin/pipelex validate bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_batch.mthds \
  --temporal > /tmp/tier2c-validate.log 2>&1; echo "EXIT=$?"
tail -20 /tmp/tier2c-validate.log
```

GREEN: `EXIT=0` and `Successfully validated bundle ...`. **Strong check** (the point of the scenario):
the worker stayed idle — it received no top-level dispatch. Capture both worker sessions and confirm
no new `WfPipeRouter` / `WfPipeRun` execution appeared for this run (split workers are the Step 2
default; fall back to `temporal-worker` for the single-worker setup):

```bash
tmux capture-pane -t temporal-worker-router -p -S -200 | grep -i WfPipeRouter   # expect: nothing new
tmux capture-pane -t temporal-worker-runner -p -S -200 | grep -i WfPipeRun      # expect: nothing new
```

RED (prove the scenario bites) — the fix is committed, so neutralize it in the working tree. Surgical:
in `pipelex/pipeline/bundle_validator.py`, inside `validate_pipes`, drop the `with
scoped_pipe_router(self._pipe_router):` wrapper so the sweep loop runs unscoped (de-indent the loop
one level). Re-run the GREEN command — expect `EXIT=1`, `Dry run failed with 1 unexpected pipe
failure(s): 'temporal_batch_test.batch_temporal_describe_topics': ... Failed to execute workflow
WfPipeRouter`, and the worker session now shows `WfPipeRouter` activity (the leak). **Restore the fix
immediately:** `git checkout -- pipelex/pipeline/bundle_validator.py`.

After this completes, tell the user:
- PASS (GREEN exits 0 **and** worker idle — no dispatch) / FAIL.
- Caveats worth stating: only a *standalone* `PipeBatch`/`PipeParallel` swept directly turns the leak
  fatal (concurrent same-id collision); a batch reached only as a sequence sub-pipe round-trips
  Temporal but passes (a false pass), so "validate exited 0" alone is **not** sufficient — the
  worker-idle check is the real assertion. Worker up vs down are **both** RED (collision
  `WorkflowAlreadyStartedError` vs no-worker `RPCError`, same `except` branch); keep the worker up to
  match production.
- The cheaper CI-automated companion to this scenario is the Mode-1 pytest
  `tests/integration/pipelex/temporal/test_validate_sweep_stays_in_process.py` (real
  `TemporalPipeRouter` as hub default, spies `WorkflowExecutor.execute_workflow`, asserts never
  called). This Mode-2 scenario is the deployment-faithful demonstration across the real API↔worker
  process boundary.

**Tier 2d — Dry-run + validation runs as ONE in-process, in-memory activity.**

Sibling to Tier 2c: where 2c proves the *direct* `/validate` sweep doesn't leak to Temporal, 2d
proves the *Temporal-dispatched* path runs the whole sweep **+** graph dry-run inside a single
activity (`act_dry_validate`, dispatched via the one-step wrapper workflow `wf_dry_validate`), in
memory, returning `{status map, GraphSpec}` in one round-trip. The submitter script below is the
same dispatch shape the Temporal-enabled API `/validate` uses.

```bash
# Server + split workers up (Mode 2). Dispatch the wrapper-workflow→activity over the parallel
# controller bundle (interesting graph: sequence → parallel fan-out → 2 branches → summary).
timeout 120 .venv/bin/python .claude/skills/temporal-e2e-validate/scripts/submit_dry_validate.py \
  --bundle tests/integration/pipelex/temporal/library_crate/temporal_parallel.mthds \
  --pipe temporal_parallel_test.temporal_parallel_sequence > /tmp/tier2d-validate.log 2>&1; echo "EXIT=$?"
tail -20 /tmp/tier2d-validate.log
```

GREEN: `EXIT=0` · the STATUS MAP lists every pipe in the bundle as `SUCCESS` · `GRAPH:` line shows a
non-empty GraphSpec (nodes for the whole controller topology) and the JSON landed at
`/tmp/tier2d-graph-spec.json`.

**Strong check (the point):** during the run the worker ran the wrapper workflow + exactly one
`act_dry_validate` and **nothing else** — NO child `WfPipeRouter`/`WfPipeRun`, NO `act_llm_gen_*`,
NO `act_assemble_tracing`/`act_flush_trace_events`. Capture both worker sessions and grep — expect
only `wf_dry_validate` / `act_dry_validate` for this run (mirrors Tier 2c's worker-idle check, but
here the one activity is expected; what must be absent is everything *nested*):

```bash
tmux capture-pane -t temporal-worker-router -p -S -200 | grep -iE "WfPipeRouter|WfPipeRun|act_llm_gen|act_assemble_tracing|act_flush_trace_events"   # expect: nothing new
tmux capture-pane -t temporal-worker-runner -p -S -200 | grep -iE "WfPipeRouter|WfPipeRun|act_llm_gen|act_assemble_tracing|act_flush_trace_events"   # expect: nothing new
```

**In-memory tracing:** no new NDJSON partition appears under `.pipelex/traces/` for the activity's
internal graph dry-run, and no DynamoDB write — the `GraphSpec` rode back on the activity result,
assembled from the in-memory log. **No usage/cost:** no cost table, no `usage_report` events.

**Best-effort graph sub-case:** dispatch a bundle with no `main_pipe` and no `--pipe` (so the graph
arm has nothing to target):

```bash
timeout 120 .venv/bin/python .claude/skills/temporal-e2e-validate/scripts/submit_dry_validate.py \
  --bundle tests/integration/pipelex/temporal/library_crate/temporal_batch.mthds \
  --no-pipe > /tmp/tier2d-nograph.log 2>&1; echo "EXIT=$?"
tail -5 /tmp/tier2d-nograph.log
```

GREEN: `EXIT=0`, full STATUS MAP, and `GRAPH: None (best-effort — validation still succeeded)`.

**Concurrency:** launch two submitter invocations in parallel (e.g. `temporal_parallel.mthds` and
`temporal_batch.mthds --no-pipe` with `--graph-out` pointing at distinct files) and confirm both
exit 0 with distinct `graph_id`s / status maps — no shared or merged trace events.

RED (prove it bites) — the fix is committed, so neutralize it in the working tree. Either arm:

- **Drop the content-generator scope:** in `pipelex/pipe_run/dry_run_pipeline.py`
  (`dry_run_pipe_in_process`), remove `scoped_content_generator(ContentGeneratorDry())` from the
  `with` line. Under Part-B leaf-mock semantics the leaf reaches the hub
  `ContentGeneratorInWorkflow` and dies with `_NotInWorkflowEventLoopError` / the strong check shows
  dispatch. (Today's pipe-level DRY mock masks this arm in Mode 2 — the CI-cheap Mode-1 companion
  `test_dry_run_graph_in_process.py::test_leaf_level_mock_stays_in_process` simulates the leaf mock
  and is the deterministic RED for it.)
- **Drop the shared event log:** in the same function, remove `scoped_event_log(event_log)` from
  the `with` line — the two-instance regression: emit and assemble no longer share the instance, the
  assembly finds zero events, and the submitter gets `EXIT=1` with `In-process dry-run of pipe '...'
  did not produce a graph spec` (the bare `PipelexError` is deliberately OUTSIDE the activity's D5
  narrow best-effort catch — a broken tracing pipeline is an infra bug and fails loudly, it does not
  silently degrade to `graph=None`).

**Restore immediately:** `git checkout -- pipelex/pipe_run/dry_run_pipeline.py`.

**API arm (after Phase 4 — the real `/validate` route in `../pipelex-api`).** With the server +
split workers up, exercise the actual route code performing the real dispatch (the sibling repo's
venv must have this pipelex installed, e.g. `cd ../pipelex-api && uv pip install -e ../<this-worktree>`):

```bash
# From ../pipelex-api: boot PYTEST-mode with temporal_enabled=True, point the dispatch at the
# e2e queue, and POST a real bundle through TestClient (full route + handler chain, real worker).
cd ../pipelex-api && timeout 120 .venv/bin/python - <<'PY'
import os
os.environ.setdefault("COMPLETION_CALLBACK_SECRET", "tier2d-placeholder")
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipelex.config import get_config
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode

BUNDLE = open("../pipelex/tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds").read()  # or any main_pipe bundle
Pipelex.make(IntegrationMode.PYTEST, temporal_enabled=True)
get_config().temporal.worker_config.default_task_queue = "temporal_task_queue"
from api.exception_handlers import register_exception_handlers
from api.routes import router as api_router
app = FastAPI(); app.include_router(api_router, prefix="/api/v1"); register_exception_handlers(app)
resp = TestClient(app).post("/api/v1/validate", json={"mthds_contents": [BUNDLE]})
print(resp.status_code, resp.json().get("graph_spec") is not None)
Pipelex.teardown_if_needed()
PY
```

GREEN: `200 True` (one round-trip returned the envelope with a worker-assembled `graph_spec`), the
worker shows only `wf_dry_validate` + one `act_dry_validate` (same strong check as above), and a
strict-mode signature bundle POSTed the same way returns **422** with
`error_type=ValidateBundleError`, `error_domain=input` — identical to the direct path. The failed
workflow must appear exactly ONCE in `temporal workflow list` (the dispatch pins
`RetryPolicy(maximum_attempts=1)` on the wrapper workflow — a deterministic validation failure
must not re-run). The bundle's graph is best-effort: a bundle with no `main_pipe` 422s on the
API-side precondition; the worker-side `graph_spec=None` arm is covered by the route's unit tests
(`tests/unit/test_validate_temporal_dispatch.py`).

After this completes, tell the user:

- PASS (GREEN exits 0 · status map all SUCCESS · non-empty GraphSpec · worker shows ONLY the
  wrapper workflow + one `act_dry_validate` · no NDJSON/DDB write · best-effort sub-case returns
  `GRAPH: None` with exit 0) / FAIL.
- The cheaper CI-automated companion is the Mode-1 pytest
  `tests/integration/pipelex/temporal/test_dry_validate_activity_in_memory.py` (real worker against
  the in-process server; zero-nested-dispatch asserted on the Temporal history; in-memory tracing
  with `make_event_log` forbidden; best-effort graph; structured `ErrorReport` on validation
  failure; concurrent isolation).

**Tier 3 — Do parallel branches execute as separate child workflows?**

This sends a PipeParallel controller that fans out into two branches (tone analysis and
length analysis), each running as its own child workflow on the worker. The branches
execute concurrently and their results merge back. The `--graph` flag here is especially
interesting: it shows cross-worker execution with child workflow branches in the
ReactFlow visualization.

```bash
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_parallel.mthds \
  --pipe temporal_parallel_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

After this completes, tell the user: PASS/FAIL, output dir, graph file path.

**Tier 4 — Can the worker handle image generation pipelines?**

**Important — split workers REQUIRED for this tier.** Run Tier 4 only when the
two scoped workers from Step 2 (`mode-2-setup.md`) are alive (`temporal-worker-router` and
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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/crazy_image_generation.mthds \
  --pipe generate_crazy_image \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Live (real image generation — required to catch payload size bugs):

```bash
timeout 600 .venv/bin/pipelex run bundle \
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
> Routing validation battery** in `routing-battery.md`.

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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/test_image_out_in.mthds \
  --pipe image_out_in \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Live (real image generation + vision — required to catch payload size bugs):

```bash
timeout 600 .venv/bin/pipelex run bundle \
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
> in `routing-battery.md`.

If any tier hangs for more than 30 seconds, check worker output. With the
recommended split workers (Step 2, `mode-2-setup.md`), capture both sessions; for the
alternative single full worker setup, capture `temporal-worker` instead:

```bash
# Split workers (default setup from Step 2, mode-2-setup.md)
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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_concept_alpha.mthds \
  --pipe alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_ALPHA=$!

timeout 120 .venv/bin/pipelex run bundle \
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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/conflict_pipe_alpha.mthds \
  --pipe pipe_alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_ALPHA=$!

timeout 120 .venv/bin/pipelex run bundle \
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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/multi_concept_alpha.mthds \
  --pipe multi_alpha_pipeline \
  --temporal --dry-run --mock-inputs --no-logo --graph &
PID_ALPHA=$!

timeout 120 .venv/bin/pipelex run bundle \
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
`writer_id="primary"`, never `act_*`.

**Cheap deterministic CLI way: `--mock-inference` (Tier 8b below).** To observe
runner-side `act_*` writer files from the CLI *without LLM spend*, use
`--mock-inference`: a LIVE run (operators dispatch `act_llm_gen_text` to the
runner exactly as a real run does) whose AI calls are faked at the inference leaf
with reportable synthetic usage. This is the deterministic, free path — prefer it
over live mode for writer-id observation, and see **Tier 8b** for the full
cross-worker cost-report assertion. The two other paths below remain valid: the
Phase 4 integration test (which substitutes the inference activity with a wrapper
that synthesizes a real `LLMJob` server-side), and live mode (real spend).

```bash
timeout 180 .venv/bin/pytest -x -v \
  tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py \
  -m temporal --temporal-server local --timeout=60 2>&1 | tail -60
```

Expected: both test cases pass —
`test_runner_usage_event_lands_in_same_ndjson_dir` (lands in same dir, with an
`__w_act_*` file) and `test_no_double_emit_in_split_worker_pool` (no
double-counting between fast path and fallback).

**To observe `act_*` writer files via the CLI**, run live mode (real LLM call —
costs money) so `act_llm_gen_text` is actually dispatched to the runner:

```bash
timeout 600 .venv/bin/pipelex run bundle \
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

### Step 5b': Tier 8b — Cross-worker cost report assembly (`--mock-inference`, free + deterministic)

#### Scope manifest — which arms to run

Tier 8b has several arms. By default, run only the free, deterministic mock arms (the **default** scope — arms A–B). If the request carries an **explicit spend opt-in** — the canonical token `full` (aliases `thorough`, `every`, `with-spend`), shown as the **full** scope in the table below — run **every** arm, including the live ones that cost real money, and report PASS/FAIL for each. Do not stop after the cheap arms when a spend opt-in is present. Do **not** treat bare "live" or "all" as the opt-in (too easily incidental; "live" also collides with the default mock arm, which already runs in LIVE mode) — if that's the only signal, confirm before spending.

Run each arm in listed order. After each, surface the asserted token totals (where the arm produces them) and PASS/FAIL, then continue. **Arm D is the exception** — it runs no assertion script and emits no `RESULT: PASS` or token totals; its pass is the *absence* of a cost table and usage events (see its sub-section), so do not treat the missing totals as a failure. For every arm that *does* run the assertion script, if it cannot reach `RESULT: PASS`, stop and report it rather than silently continuing.

| # | Arm | Scope | Spend | Expected assertion |
|---|---|---|---|---|
| A | **Mock primary** — `--mock-inference` `native_text_sequence` | default + full | free | 2 events / 200 input / 100 output, `--expected-model-type llm --require-fallback` |
| B | **Cross-child fan-out** — `--mock-inference` `temporal_parallel` | default + full | free | 3 events / 300 input / 150 output, `--expected-model-type llm --require-fallback` (the CLI assert checks the summed total, **not** workflow-span; the cross-child guarantee itself is enforced by the pytest counterpart `test_split_worker_cross_child_usage.py`) |
| C | **CSV un-truncated cross-check** — flip `reporting_config.is_generate_cost_report_file_enabled=true`, rerun arm A, confirm CSV totals == NDJSON totals, restore to `false` | full | free | `csv tokens` line matches NDJSON totals |
| D | **`--no-costs` negative gate** | full | free | no cost table, no `usage_report` events, `reactflow.html` still assembles |
| E | **Live LLM arm** — drop `--mock-inference` on `native_text_sequence` | full | **real** | non-zero total, real `model_names` (not `mock_inference`), `--require-fallback --require-nonzero` |
| F | **Live img-gen arm** — run a Tier 4/5 image bundle live with `--graph --costs` | full | **real** | `--expected-model-type img_gen --require-fallback --require-nonzero` |
| G | **Live extract arm** — run the extract bundle `pdf_extract_page_views.mthds` (`--pipe pdf_extract_with_page_views`) live against the plain split workers with `--graph --costs` | full | **real** | `--expected-model-type extract --require-fallback --require-nonzero` |

Arms F and G validate non-LLM usage, which `--mock-inference` cannot reach (the mock leaves raise `MockInferenceUnsupportedError`), so they are **live-only** — they are the sole way to prove img-gen / extract token usage crosses the runner fallback and aggregates into the cost report. Each arm's full command + assertion is detailed in the sub-sections below; arms A/C map to "Primary check", B to "Cross-child aggregation", D to "Negative check", E to "Live arm", F/G to "Non-LLM cross-worker cost". Arms F and G run their bundles on the **same plain router+runner split workers** as the other arms — they do **not** need the routing battery's multi-queue (`q_extract` / `q_image_gen`) setup. On plain split workers the img-gen / extract activity runs on the runner and emits via the `act_*` fallback, which is exactly what `--require-fallback` checks.

Tier 8 (Step 5b above — the writer-id landing pytest) is the precursor to all of these and should pass first under any scope.

---

Tier 8 proves a runner-side `UsageReportEvent` *lands* in the NDJSON partition.
Tier 8b proves the next link end-to-end: those cross-worker usage events
*assemble* onto `PipeOutput.tokens_usages` (via `act_assemble_tracing` with
`assemble_usage=True`) and the submitter renders a **single** end-of-run cost
report covering usage from all workers — with **no LLM spend**.

**Why `--mock-inference` and not `--dry-run`.** Dry-run instantiates
`ContentGeneratorDry` inside the workflow body *on the router* and never
dispatches `act_llm_gen_text` to the runner (Tier 8 note), and its usage is
zero-token → the cost report is *suppressed*. `--mock-inference` keeps
`run_mode=LIVE` so operators dispatch the real `act_llm_gen_text` to the runner
exactly like a paid run; only the inference *leaf* is faked, emitting reportable
non-zero synthetic usage (model `mock_inference`). So the runner emits `act_*`
usage events AND the report is non-suppressed — the one thing dry-run can't
validate cheaply.

**Requires split router+runner workers** (Step 2 in `mode-2-setup.md`). The point
is that the usage events originate on the *runner* process and must aggregate
into the report assembled for the *router*/submitter. `--mock-inference` is on the
main `run` subcommands (pipe/method/bundle) and is mutually exclusive with
`--dry-run`.

**Primary check — both artifacts assemble from one event read (D3):**

```bash
timeout 180 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --mock-inference --no-logo --graph --costs 2>&1 | tail -30
echo "EXIT=$?"
```

Expect, at the end of the submitter output:

- A Rich **cost table** with model `mock_inference`, non-zero input/output token
  counts, and a run total (the synthetic per-call counts are
  `MOCK_INFERENCE_NB_TOKENS_BY_CATEGORY = {INPUT: 100, OUTPUT: 50}`, so a
  2-LLM-step sequence totals 200 input / 100 output).
- A `reactflow.html` for the run (graph assembles from the *same* event read).
- Exit 0.

Then **assert the numbers** (don't eyeball — the terminal table truncates wide
columns to `0 … …`). The `assert_cross_worker_cost.py` helper sums input/output
tokens straight from the NDJSON usage events, counts them, checks a runner `act_*`
writer engaged, and (if a CSV report exists) cross-checks the un-truncated CSV
totals. For mock-inference the per-call counts are fixed
(`MOCK_INFERENCE_NB_TOKENS_BY_CATEGORY = {INPUT: 100, OUTPUT: 50}`), so a
2-LLM-step sequence must total exactly 2 events / 200 input / 100 output:

```bash
RUN_ID=$(ls -t .pipelex/traces/ | head -1)
ls -la .pipelex/traces/$RUN_ID/
.venv/bin/python .claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py \
  --run-dir .pipelex/traces/$RUN_ID \
  --expected-events 2 --expected-input 200 --expected-output 100 \
  --expected-model-type llm --require-fallback
```

Expect `RESULT: PASS`, with:

- At least one `wf_*__w_act_{pid}_{uuid}.ndjson` file (runner-side) carrying
  `usage_report` events with `writer_id` starting `act_` (the `--require-fallback`
  gate), alongside router-side `wf_*.ndjson` with `writer_id="primary"`.
- The `usage events` count equal to the number of LLM steps (one per mocked
  `act_llm_gen_text`), no double-count between the fast path and the fallback.
- `total tokens : input=200 output=100`.

**Un-truncated CSV cross-check (optional but recommended).** The Rich console
table truncates; the CSV does not. Enable
`reporting_config.is_generate_cost_report_file_enabled = true` in
`.pipelex/pipelex.toml` before the run, then the run also writes
`reports/cost_report*.csv`. The script auto-detects it and asserts the CSV token
totals equal the NDJSON totals (`csv tokens` line in its output). Restore the
flag to `false` afterwards.

**Cross-child aggregation (A+B+C → one report).** Run a fan-out bundle so usage
from multiple child workflows aggregates into a single submitter report:

```bash
timeout 180 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_parallel.mthds \
  --pipe temporal_parallel_sequence \
  --temporal --mock-inference --no-logo --graph --costs 2>&1 | tail -30
echo "EXIT=$?"
```

Expect a single end-of-run cost table whose token totals sum the parent and both
child-workflow branches — not one table per branch. Assert it numerically: the
parallel bundle has three LLM steps (`branch_tone`, `branch_length`,
`summarize_results`), so 3 events / 300 input / 150 output, and usage must span
**more than one workflow** (cross-child):

```bash
RUN_ID=$(ls -t .pipelex/traces/ | head -1)
.venv/bin/python .claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py \
  --run-dir .pipelex/traces/$RUN_ID \
  --expected-events 3 --expected-input 300 --expected-output 150 \
  --expected-model-type llm --require-fallback
```

The pytest counterpart for this cross-child aggregation (no spend) is
`tests/integration/pipelex/temporal/tracing/test_split_worker_cross_child_usage.py`.

**Negative check — `--no-costs` gates costs only, graph unaffected:**

```bash
timeout 180 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --mock-inference --no-logo --graph --no-costs 2>&1 | tail -30
echo "EXIT=$?"
RUN_ID=$(ls -t .pipelex/traces/ | head -1)
grep -l '"event_kind":"usage_report"' .pipelex/traces/$RUN_ID/*.ndjson || echo "No usage_report events (expected with --no-costs)"
ls results/*/reactflow.html 2>/dev/null && echo "graph still rendered (expected)"
```

Expect: **no** cost table rendered, **no** `usage_report` events in the NDJSON
(the usage event-log isn't wired when `--no-costs`), but the `reactflow.html`
still assembles — proving `--costs` gates only the cost channel, independent of
`--graph`.

**Live arm (real spend, opt-in)** — mirrors Tier 8's live block for the
real-payload case. Drop `--mock-inference` so the real `act_llm_gen_text` runs on
the runner and bills real tokens:

```bash
timeout 600 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --no-logo --graph --costs 2>&1 | tail -30
```

Real token counts are not predictable, so assert non-zero rather than exact —
the run still must capture real provider tokens, cross the runner boundary, and
aggregate to a non-zero total:

```bash
RUN_ID=$(ls -t .pipelex/traces/ | head -1)
.venv/bin/python .claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py \
  --run-dir .pipelex/traces/$RUN_ID \
  --expected-model-type llm --require-fallback --require-nonzero
```

Expect `RESULT: PASS` with non-zero `total tokens` and a real `model_names` entry
(not `mock_inference`). The pytest counterpart for this real-inference cross-worker
path (gated, opt-in spend) is
`tests/integration/pipelex/temporal/tracing/test_split_worker_real_inference_cost.py`
(marked `inference`/`llm`; the no-spend counterpart is
`tests/integration/pipelex/temporal/tracing/test_mock_inference_temporal.py`).

**Non-LLM cross-worker cost (img-gen / extract — live only).** `--mock-inference`
cannot cover image generation or extraction: their mock leaves raise
`MockInferenceUnsupportedError`, so non-LLM usage only crosses the runner boundary
on a real run. The img-gen / extract live tiers (Tiers 4 / 5 / 10c) already
exercise those activities cross-process but never check the cost numbers. After
running one of those live tiers with `--graph --costs` against split workers,
assert its run dir surfaced non-zero non-LLM usage with the right model handle:

```bash
RUN_ID=$(ls -t .pipelex/traces/ | head -1)
# --expected-model-type img_gen for an image-gen bundle, extract for an extract bundle
.venv/bin/python .claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py \
  --run-dir .pipelex/traces/$RUN_ID \
  --expected-model-type img_gen --require-fallback --require-nonzero
```

Expect `RESULT: PASS` proving image-gen/extract token usage (not just LLM) is
captured, emitted via the runner fallback, and aggregated into the submitter's
cost report. The no-spend unit counterparts (img-gen/extract usage through the
fallback + aggregator) are
`tests/unit/pipelex/reporting/test_emit_runner_fallback_non_llm.py` and
`tests/unit/pipelex/tracing/test_non_llm_usage_aggregation.py`.

After each run, tell the user: the script's `RESULT: PASS/FAIL`, whether the cost
table rendered, the distinct `writer_id` set (must include an `act_*`), the
usage-event count and the summed input/output tokens (NDJSON, and CSV if
enabled), and the graph file path.

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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/structured_output_sequence.mthds \
  --pipe generate_invoice_single \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

```bash
timeout 120 .venv/bin/pipelex run bundle \
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
timeout 180 .venv/bin/pytest -x -v \
  tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py \
  -m temporal --temporal-server local --timeout=60 2>&1 | tail -60
```

After this completes, tell the user: PASS/FAIL. The test asserts via
`WorkflowHandle.fetch_history()` that exactly two `ActivityTaskScheduled`
events appear with `activity_id` ending in `-pages` and `-render-page-views`.
For manual Temporal Web UI inspection, point `temporal-worker-router` /
`temporal-worker-runner` at the same dev server and inspect the workflow's
event timeline — the two scheduled activities should be visible with their
distinct activity_ids.

### Step 5e: Tier 12 — Deeply-nested controller stack (CV batch screening)

Validates the full pipelex-demos example 21 pipeline through Temporal: a
nested PipeSequence -> PipeSequence (job-offer prep) + PipeBatch (per-CV
fan-out) -> PipeSequence (extract + analyze + match) over PipeExtract +
PipeLLM operators. This is the canonical "real-world" e2e bundle for the
skill — controller composition that the other tiers only exercise piecewise.

The pytest counterpart lives at
`tests/integration/pipelex/temporal/library_crate/test_wf_cv_batch_screening.py`
(in-process server, dry mode). The direct-mode (no Temporal) e2e counterpart
lives at `tests/e2e/pipelex/cv_batch_screening/test_cv_batch_screening.py`.

Dry-run (CLI mocks inputs — no PDFs needed):

```bash
timeout 180 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/cv_batch_screening.mthds \
  --pipe batch_analyze_cvs_for_job_offer \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Live (real Azure Doc Intel extract + LLM analysis — uses `John-Doe-CV.pdf`
and `Job-Offer.pdf` from `tests/data/documents/`):

```bash
timeout 900 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/cv_batch_screening.mthds \
  --pipe batch_analyze_cvs_for_job_offer \
  --inputs tests/integration/pipelex/temporal/library_crate/cv_batch_screening_inputs.json \
  --temporal --no-logo --graph
```

After completion, tell the user: PASS/FAIL, output dir, graph file path. The
generated ReactFlow graph is unusually rich for this pipeline (nested
PipeSequence containers + PipeBatch fan-out edges + per-step extract/LLM
nodes) and is the recommended one to open at the end of the run:

```bash
open results/batch_analyze_cvs_for_job_offer_output_01/reactflow.html
```

If the live run errors with `Extract choice '...' was not found in the model
deck`, the deck is not loading Azure Doc Intel — fix the deck before falling
back to a different handle; user preference is Azure Doc Intel via the
Pipelex Gateway, period (do not substitute `mistral-ocr` / `deepseek-ocr`).

### Step 5f: Tiers 13–16 — Error propagation across the activity → workflow → submitter boundary

These four tiers validate the error-handling deliverable in a *true* 3-process
setup: a worker-side failure must travel back to the submitter carrying its
`ErrorReport` — the submitter must surface the *real classified inner error*,
not a bare "workflow failed" wrapper. The in-process pytest suite (Mode 1 Step 2b
in `SKILL.md`) asserts the structured `ErrorReport` fields directly; these tiers
prove the same survives real OS-process serialization. Tiers 13–15 fail a
*single* top-level activity, one per activity family (LLM, extract, image-gen);
Tier 16 fails inside a fanned-out child workflow.

**Submitter note.** The human CLI (`pipelex run bundle`) is the only CLI that
dispatches to Temporal — the agent CLI has no `--temporal`. It prints a flat
message, so the PASS check is at the message level. Precise field-level
assertions (`error_category` etc.) belong to Mode 1 Step 2b in `SKILL.md`.

**Inducing the failure — why `.env` must be edited.** The worker is a separate
process; you make its inference calls fail by giving it invalid credentials.
A shell-env prefix on the `tmux` command does NOT work: Pipelex loads `.env`
with `override=True` (`pipelex/system/environment.py`), so `.env` always wins
over the shell env. The reliable method is to temporarily append invalid keys
to `.env`, start the worker (it captures the tampered env at boot), then restore
`.env` immediately — the submitter and everything after run with a clean `.env`,
while the already-booted worker keeps the bad keys.

**Each tier owns the task queue exclusively.** The bad-credential worker must be
the *only* worker polling `temporal_task_queue` — else a healthy shared worker
picks up the activity and succeeds. Kill all workers first; restart the shared
ones (Step 2 in `mode-2-setup.md`) only if you continue to later tiers (Step 6 restarts its own).

**Start the bad-credential worker** — shared by Tiers 13–16, start it once:

```bash
# Back up .env, append invalid inference credentials, start the worker, restore .env
cp .env /tmp/dotenv-tier-err-bak
cat >> .env << 'EOF'

# --- temporal-e2e-validate Tier 13-16: invalid inference credentials (temporary) ---
OPENAI_API_KEY=invalid-key-tier-err
PIPELEX_GATEWAY_API_KEY=invalid-key-tier-err
PIPELEX_INFERENCE_API_KEY=invalid-key-tier-err
ANTHROPIC_API_KEY=invalid-key-tier-err
GOOGLE_API_KEY=invalid-key-tier-err
AZURE_API_KEY=invalid-key-tier-err
EOF
pkill -f "pipelex.temporal.worker_cli" 2>/dev/null; sleep 1
tmux kill-session -t temporal-worker-err 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-err \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
for attempt in $(seq 1 30); do
  if tmux capture-pane -t temporal-worker-err -p 2>/dev/null | grep -q "Temporal Worker started"; then break; fi
  if [ "$attempt" -eq 30 ]; then
    echo "TIMEOUT: temporal-worker-err did not start within 30s — last 50 lines:"
    tmux capture-pane -t temporal-worker-err -p -S -50
  fi
  sleep 1
done
cp /tmp/dotenv-tier-err-bak .env && echo ".env restored — the worker holds the invalid keys"
grep -q "tier-err" .env && echo "WARNING: .env still tampered — restore manually" || echo ".env clean"
```

**Tier 13 — LLM activity error propagation**

Submits `native_text_sequence` live. The first `act_llm_gen_text` call fails
provider-side with a 401 auth error — classified `CONFIGURATION` (non-retryable,
so no retry storm), converted to `TemporalError`, carried back as an
`ErrorReport`. The auth rejection happens before any tokens are billed — free.

```bash
timeout 600 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --no-logo > /tmp/tier13.log 2>&1
echo "EXIT=$?"
tail -25 /tmp/tier13.log
```

Report to the user:

- **PASS** = non-zero exit (within ~30s — `CONFIGURATION` is non-retryable), and
  the final `Failed to execute pipeline '...': <cause>` line carries the *real
  inner error* — an authentication / `401` / `Invalid API Key` message. That
  proves the worker's `ErrorReport` crossed the boundary: without recovery the
  cause would be a bare workflow-failed wrapper with no inner detail. Confirm on
  the worker:
  `tmux capture-pane -t temporal-worker-err -p -S -200 | grep -iE "act_llm_gen_text|TemporalError|authentication|401"`.
- **FAIL** = hangs > 60s; exits 0 (a stray healthy worker stole the activity —
  check no other worker polls the queue); or the cause is only a generic
  workflow-failed wrapper with no inner provider error (see "Interpreting
  failures").

Note: the string `Failed to execute workflow WfPipeRun:` appears in a normal
`ERROR` log line — that is expected. The signal is the *inner cause* after it.

**Tier 14 — non-LLM (extract) activity error propagation**

The counterpart through a non-LLM activity, against the *same* bad-credential
worker. `act_extract_gen_extract_pages` fails on the worker; the `ErrorReport`
must cross the same way. Mirrors the LLM + non-LLM split that
`test_activity_error_boundary.py` covers in-process.

Create the inputs JSON if it does not exist:

```bash
cat > /tmp/pdf_extract_inputs.json << EOF
{
  "source_pdf": {
    "concept": "native.Document",
    "content": { "url": "$PWD/tests/data/documents/Job-Offer.pdf" }
  }
}
EOF
```

```bash
timeout 600 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/pdf_extract_page_views.mthds \
  --pipe pdf_extract_with_page_views \
  --inputs /tmp/pdf_extract_inputs.json \
  --temporal --no-logo > /tmp/tier14.log 2>&1
echo "EXIT=$?"
tail -25 /tmp/tier14.log
```

Report to the user:

- **PASS** = non-zero exit, and the `Failed to execute pipeline '...': <cause>`
  line carries the real extract auth error (`Extract service error ... 401 ...
  Invalid API Key`). Confirm on the worker:
  `tmux capture-pane -t temporal-worker-err -p -S -200 | grep -iE "act_extract_gen_extract_pages|TemporalError|authentication|401"`.
- **FAIL** = same modes as Tier 13.

**Tier 15 — image-generation activity error propagation**

The counterpart through the image-generation activity (`act_img_gen_images`),
against the *same* bad-credential worker. The error boundary
(`@convert_pipelex_errors`) is wired on every in-scope activity — Tier 13 proves
it for LLM, Tier 14 for extract, this tier closes it for image generation.

`generate_image` is a single `PipeImgGen` step with a static prompt, so
`act_img_gen_images` is the first (and only) inference activity dispatched — a
failure here is unambiguously the image-gen path, not a preceding LLM step. The
image model (`gpt-image-1-mini`) rejects the request on the tampered
OpenAI / Gateway key before any image is billed — free.

```bash
timeout 600 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/pipes/pipelines/test_image_out_in.mthds \
  --pipe generate_image \
  --temporal --no-logo > /tmp/tier15.log 2>&1
echo "EXIT=$?"
tail -25 /tmp/tier15.log
```

Report to the user:

- **PASS** = non-zero exit, and the `Failed to execute pipeline '...': <cause>`
  line carries the real image-gen auth error (`401` / `Invalid API Key` from the
  image model). Confirm on the worker:
  `tmux capture-pane -t temporal-worker-err -p -S -200 | grep -iE "act_img_gen_images|TemporalError|authentication|401"`.
- **FAIL** = same modes as Tier 13.

**Tier 16 — error propagation out of a fanned-out child workflow (PipeBatch)**

Tiers 13–15 fail a *single* top-level activity. This tier proves the report also
crosses when the failure happens *inside a fanned-out child workflow*: a
`PipeBatch` dispatches one child workflow per item, and each child's
`act_llm_gen_text` fails on the bad-credential worker. The first failing child's
`ErrorReport` must propagate up through the batch controller → `WfPipeRouter` →
submitter — not collapse into a generic "a batch item failed" wrapper.

Running the `PipeBatch` pipe (`batch_temporal_describe_topics`) directly — not
the wrapping `temporal_batch_sequence` — is deliberate: the sequence would fail
at its first LLM step (topic generation) before ever reaching the fan-out.
Feeding the topic list via `--inputs` skips topic generation so the batch
fan-out is the first inference dispatched.

Create the inputs JSON:

```bash
cat > /tmp/batch_topics_inputs.json << 'EOF'
{
  "topics": {
    "concept": "temporal_batch_test.Topic",
    "content": ["science", "history", "music"]
  }
}
EOF
```

```bash
timeout 600 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_batch.mthds \
  --pipe batch_temporal_describe_topics \
  --inputs /tmp/batch_topics_inputs.json \
  --temporal --no-logo > /tmp/tier16.log 2>&1
echo "EXIT=$?"
tail -25 /tmp/tier16.log
```

Report to the user:

- **PASS** = non-zero exit, and the `Failed to execute pipeline '...': <cause>`
  line carries the real per-branch auth error (`401` / `Invalid API Key`) —
  proving the child workflow's `ErrorReport` survived the fan-in, not a generic
  batch wrapper. Confirm on the worker:
  `tmux capture-pane -t temporal-worker-err -p -S -200 | grep -iE "act_llm_gen_text|temporal_describe_topic|TemporalError|401"`.
- **FAIL** = hangs > 60s (a retry storm — the per-branch failure should be
  non-retryable `CONFIGURATION`); exits 0 (a stray healthy worker stole a
  branch activity); or the cause is a generic batch/workflow-failed wrapper with
  no inner provider error (the child `ErrorReport` did not cross the fan-in —
  the exact gap this tier exists to catch).

**Teardown** (after Tiers 13–16):

```bash
tmux kill-session -t temporal-worker-err 2>/dev/null
# Safety net: ensure .env was restored, then drop the backup
if [ -f /tmp/dotenv-tier-err-bak ]; then
  grep -q "tier-err" .env && cp /tmp/dotenv-tier-err-bak .env && echo ".env restored from backup"
  rm /tmp/dotenv-tier-err-bak
fi
grep -q "tier-err" .env && echo "WARNING: .env still tampered" || echo ".env clean"
```

If you continue to Step 6 or later tiers, restart the shared worker(s) per Step 2 in `mode-2-setup.md`.

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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

```bash
timeout 120 .venv/bin/pipelex run bundle \
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
timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/large_payload_sequence.mthds \
  --pipe large_payload_sequence \
  --temporal --dry-run --mock-inputs --no-logo --graph
```

Live (real LLM calls — produces larger payloads, better stress test):

```bash
timeout 600 .venv/bin/pipelex run bundle \
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

List all graph files and present a summary table with results. Tier 10a–10c are defined in `routing-battery.md` and Scenarios A–F in `queue-options-battery.md` — include those rows only if you ran those batteries:

```bash
ls results/*/reactflow.html
```

| Test | What it proved | Status | Graph | Payload warnings |
|------|---------------|--------|-------|-----------------|
| Tier 1: Sequence | Worker can unpack crate and run a pipe sequence | PASS/FAIL | path | — |
| Tier 2: Hydration | Worker handles dynamic concepts it has never seen | PASS/FAIL | path | — |
| Tier 2b: Cross-process registry | `act_deliver` decodes hydrated `pipe_output` on runner (forced via `delivery_assignment`) | PASS/FAIL | — | — |
| Tier 2c: Validate sweep stays in-process | `validate bundle --temporal` over a standalone `PipeBatch` exits 0 **and** the worker received no `WfPipeRouter` dispatch (the sweep never leaks to Temporal) | PASS/FAIL | — | — |
| Tier 2d: Dry-run+validate as one in-memory activity | the Temporal-dispatched /validate runs the whole sweep + graph dry-run inside ONE in-process activity (zero nested dispatch), traces the graph in memory (no NDJSON/DDB), returns {status, GraphSpec}; best-effort graph → None on failure | PASS/FAIL | path | — |
| Tier 3: Parallel | Branches execute as concurrent child workflows | PASS/FAIL | path | — |
| Tier 4: ImgGen | Image generation pipeline works through Temporal | PASS/FAIL | path | yes/no |
| Tier 5: Image flow | Generated image flows as input to next pipe step | PASS/FAIL | path | yes/no |
| Tier 6: Codec transparency | Existing pipelines work unchanged with codec enabled | PASS/FAIL | path | — |
| Tier 7: Large payload | Multi-step pipeline with codec stress test | PASS/FAIL | path | — |
| Tier 8: Cross-worker usage | Runner-side `UsageReportEvent` lands in same NDJSON dir with `act_*` writer_id (live mode or integration test) | PASS/FAIL | — | — |
| Tier 8b: Cross-worker cost report | `--mock-inference` (free): runner-side usage assembles onto `PipeOutput.tokens_usages` and the submitter renders a single non-suppressed cost report (model `mock_inference`); `--no-costs` renders none while `--graph` still assembles. **Numeric assertion** via `scripts/assert_cross_worker_cost.py` (sums NDJSON usage tokens, checks count + `act_*` fallback + optional CSV cross-check) — mock: 2 events/200 input/100 output; parallel: 3/300/150; live arms `--require-nonzero`; img-gen/extract `--expected-model-type` (live only) | PASS/FAIL | path | — |
| Tier 9: Object gen cross-process | `act_llm_gen_object` / `act_llm_gen_object_list` survive the JSON round-trip with nested fields intact | PASS/FAIL | path | — |
| Tier 10a: Multi-activity routing | `activity_queues.default` routes both `act_llm_gen_text` and `act_img_gen_images` to their dedicated worker pools; default runner sees 0 hits for either | PASS/FAIL/SKIPPED | — | — |
| Tier 10b: Per-handle routing | `activity_queues.by_handle` overrides the activity default per model handle — two distinct handles in one workflow land on two distinct workers | PASS/FAIL/SKIPPED | path | — |
| Tier 10c: Two activities, one route | `act_extract_gen_extract_pages` + `act_render_page_views` (no routing key) both land on a shared dedicated queue via Azure Doc Intel through Pipelex Gateway | PASS/FAIL | — | — |
| Tier 11: Extract two-activity | `act_extract_gen_extract_pages` + `act_render_page_views` dispatched cross-process with distinct activity_ids | PASS/FAIL | — | — |
| Tier 12: CV batch screening | Deeply-nested controller stack (PipeSequence → PipeSequence + PipeBatch → PipeSequence) over PipeExtract + PipeLLM (pipelex-demos example 21) | PASS/FAIL | path | — |
| Tier 13: LLM error propagation | A worker-side LLM auth failure crosses activity→workflow→submitter; submitter shows the real error, not the generic `"Failed to execute workflow"` wrapper | PASS/FAIL | — | — |
| Tier 14: Extract error propagation | Same for a non-LLM (`act_extract_gen_extract_pages`) activity failure | PASS/FAIL | — | — |
| Tier 15: Image-gen error propagation | Same for the image-generation (`act_img_gen_images`) activity failure | PASS/FAIL | — | — |
| Tier 16: Batch child-workflow error propagation | A per-branch failure inside a `PipeBatch` fan-out child workflow crosses the fan-in carrying its `ErrorReport`, not a generic batch wrapper | PASS/FAIL | — | — |
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
from Step 2 in `mode-2-setup.md` are the default — fall back to `temporal-worker`
only if you used the single full worker setup):

```bash
tmux capture-pane -t temporal-worker-router -p -S -200
tmux capture-pane -t temporal-worker-runner -p -S -200
```
