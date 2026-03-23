---
name: temporal-diagnose
description: >
  Two modes for working on the Temporal worker library loading bug.
  DIAGNOSE mode: run the 3-terminal Temporal dev setup (server + worker + job),
  observe the failure, interpret errors. Use when the user says "test temporal",
  "run temporal", "diagnose temporal", "temporal dev", "reproduce the temporal bug",
  "check if temporal works", or pastes Temporal worker/submitter output to interpret.
  FIX mode: discuss architecture, design the solution, plan implementation, make
  code changes. Use when the user says "fix temporal", "let's discuss a fix",
  "design the temporal fix", "implement the temporal fix", "plan the temporal
  solution", or wants to iterate on the worker library loading solution.
  Always use this skill when the conversation touches the Temporal worker library
  problem, get_required_pipe failures on the worker, or mthds_contents not reaching
  the worker.
---

# Temporal Worker Library — Diagnose & Fix

This skill has two modes. Determine which one from the user's prompt:

- **"diagnose"**, **"test"**, **"run"**, **"reproduce"**, **"check"** → DIAGNOSE mode
- **"fix"**, **"discuss"**, **"design"**, **"implement"**, **"plan"**, **"solution"** → FIX mode

If ambiguous, ask the user: "Do you want to diagnose (run the setup and observe) or discuss the fix?"

Read `references/temporal-worker-problem.md` before proceeding — it explains the
root cause, code paths, and expected error patterns.

## How Claude Code runs everything

Claude Code handles all three processes. Do NOT ask the user to open terminals
or run commands — do it yourself.

Use **tmux** to manage the long-running processes (server and worker) in named
sessions. This lets you start them, run the job submitter, and then capture
output from all three to diagnose.

| Process | tmux session | Raw command | Lifecycle |
|---------|-------------|-------------|-----------|
| Temporal server | `temporal-server` | `temporal server start-dev` | Long-running, stays up across iterations |
| Temporal worker | `temporal-worker` | `PIPELEXPATH=<bundle_dir> .venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed` | Long-running, restart after code changes |
| Job submitter | (inline Bash) | `make trund` / `make trun` | Runs and exits |

**Important**: The server and worker are **long-running processes that never exit**.
They block the shell they run in. That is why they run inside tmux sessions, not
inline. The submitter (`make trund` / `make trun`) is the only process that runs to
completion and exits — run it directly via Bash, not in tmux.

**Why raw commands in tmux**: tmux sessions run in a bare shell without the
Makefile's variable resolution (`$(VENV_PYTHON)`, `$(call PRINT_TITLE,...)`).
Using `make ts` or `make tw` inside tmux will fail. Always use the raw commands
shown above for tmux sessions. The `make` targets are only for the job submitter
which runs in Claude Code's own shell.

### tmux cheatsheet

**Start a session:**
```bash
tmux new-session -d -s temporal-server 'temporal server start-dev'
```

**Check if running:**
```bash
tmux has-session -t temporal-server 2>/dev/null && echo "running" || echo "not running"
```

**Read output** (last N lines):
```bash
tmux capture-pane -t temporal-worker -p -S -100
```

**Kill and restart** (e.g., to pick up code changes):
```bash
tmux kill-session -t temporal-worker
tmux new-session -d -c "$PWD" -s temporal-worker 'PIPELEXPATH=tests/integration/pipelex/pipes/controller/pipe_sequence .venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
```

If tmux is not installed, fall back to asking the user to run the server and
worker in separate terminals.

---

## DIAGNOSE Mode

Run the 3-process Temporal development setup and interpret results.

### Prerequisites

Verify these yourself (via Bash):
1. `tmux` installed: `which tmux`
2. `temporal` CLI installed: `which temporal`

### Step 1: Start the Temporal server

First check if a server is already running (possibly outside tmux from a previous
session or another terminal):
```bash
curl -s http://localhost:8233 > /dev/null && echo "running" || echo "not running"
```

If **running**: skip to step 2. The server is already up — no need to start it again.

If **not running**: start it in a tmux session:
```bash
tmux new-session -d -s temporal-server 'temporal server start-dev'
```
Sleep **3 seconds**, then verify:
```bash
sleep 3 && curl -s http://localhost:8233 > /dev/null && echo "running" || echo "not running"
```

Do NOT try to start the server if port 7233 is already in use — it will fail with
a bind error, the tmux session will exit immediately, and subsequent `capture-pane`
calls will fail.

### Step 2: Start the worker

```bash
tmux has-session -t temporal-worker 2>/dev/null || \
  tmux new-session -d -s temporal-worker \
  'cd $PWD && PIPELEXPATH=tests/integration/pipelex/pipes/controller/pipe_sequence .venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
```

The worker is also long-running and never exits. Sleep **4 seconds** (no more),
then capture the pane:
```bash
sleep 4 && tmux capture-pane -t temporal-worker -p -S -30
```
Look for `Temporal Worker started for 'temporal_task_queue'`.

### Step 3: Submit a job

Run the job submitter. It connects to Temporal, submits the workflow, and **waits
for the result**. If the worker fails to process the job (e.g., deserialization
error), the submitter may hang for a long time waiting for a response that never
comes. Run it in the background so you can check worker output while it's waiting.

Dry run (no real LLM calls):
```bash
TEMPORAL_BUNDLE="tests/integration/pipelex/pipes/controller/pipe_sequence/pipe_sequence_1.mthds"
tmux has-session -t temporal-submitter 2>/dev/null || \
  tmux new-session -d -s temporal-submitter \
  "cd $PWD && .venv/bin/pipelex run bundle $TEMPORAL_BUNDLE --temporal --dry-run --mock-inputs --no-logo"
```

Or for real LLM execution:
```bash
TEMPORAL_BUNDLE="tests/integration/pipelex/pipes/controller/pipe_sequence/pipe_sequence_1.mthds"
tmux has-session -t temporal-submitter 2>/dev/null || \
  tmux new-session -d -s temporal-submitter \
  "cd $PWD && .venv/bin/pipelex run bundle $TEMPORAL_BUNDLE --temporal --mock-inputs --no-logo"
```

Both default to `pipe_sequence_1.mthds`. To target a specific pipe, add `--pipe <pipe_code>`.
Override the bundle by changing `TEMPORAL_BUNDLE`.

### Step 4: Diagnose the output

Read the submitter output (from step 3) AND the worker output:
```bash
tmux capture-pane -t temporal-worker -p -S -200
```

**Expected failure (bug not yet fixed):**

There are two failure layers, both caused by the missing library on the worker.
See `references/temporal-worker-problem.md` for details.

**Layer 1 — Deserialization failure** (hits first):
1. The PipeJob's WorkingMemory contains Stuff objects with dynamically-generated
   concept content classes (e.g., `RawText` inheriting from `TextContent`)
2. These classes are generated during library loading by `ConceptFactory` /
   `StructureGenerator` and registered with Kajson's class registry
3. On the worker, the library was never loaded → these classes don't exist →
   Kajson fails with `KajsonDecoderError: Class 'RawText' not found in module 'builtins'`
4. Temporal wraps this as `RuntimeError: Failed decoding arguments`
5. The submitter may hang waiting for a result that never comes

**Layer 2 — Library resolution failure** (would hit after Layer 1 is fixed):
1. `WfPipeRouter.run()` receives the PipeJob with the top-level PipeSequence
2. `PipeSequence.run_pipe()` calls `get_required_pipe("clean_text")`
3. `library_manager` singleton is empty on the worker → error
4. Propagates as `TemporalError` / `ActivityError` to the submitter

The submitter output will show a Temporal workflow failure (or hang indefinitely
for Layer 1 failures).

**After fix is applied (success looks like):**
- Submitter: successful pipeline result printed to stdout
- Worker (`tmux capture-pane`): logs showing pipe execution steps
- Temporal UI (http://localhost:8233): completed workflow with result

### Step 5: Iterate

1. Kill and restart the worker (to pick up code changes):
   ```bash
   tmux kill-session -t temporal-worker
   tmux new-session -d -c "$PWD" -s temporal-worker 'PIPELEXPATH=tests/integration/pipelex/pipes/controller/pipe_sequence .venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
   sleep 5
   ```
2. Make code changes
3. Run `make trund` again and read the result
4. Capture worker output: `tmux capture-pane -t temporal-worker -p -S -200`
5. Repeat

The server session (`temporal-server`) stays running across iterations.

### Cleanup

When done with the entire session:
```bash
tmux kill-session -t temporal-worker 2>/dev/null
tmux kill-session -t temporal-server 2>/dev/null
```

### Test bundles for different pipe controllers

| Controller | Bundle path |
|------------|-------------|
| PipeSequence | `tests/integration/pipelex/pipes/controller/pipe_sequence/pipe_sequence_1.mthds` |
| PipeCondition | `tests/integration/pipelex/pipes/controller/pipe_condition/pipe_condition_1.mthds` |
| PipeBatch | `tests/integration/pipelex/pipes/controller/pipe_batch/uppercase_transformer.mthds` |
| PipeParallel | `tests/integration/pipelex/pipes/controller/pipe_parallel/pipe_parallel_1.mthds` |

---

## FIX Mode

Discuss architecture, design choices, and implementation for solving the worker
library loading problem. Stay in discussion/planning territory — do NOT jump to
code changes unless the user explicitly says to implement.

### What you must understand first

Read `references/temporal-worker-problem.md` thoroughly. The core tension:
- `pipeline_run_setup()` loads the library into `library_manager` — but only in the API process
- PipeJob carries the serialized top-level pipe, but child pipes are resolved by code at runtime
- On the worker, `get_required_pipe()` finds an empty library

### Design dimensions to discuss with the user

1. **Where does the library load on the worker?**
   - At worker startup (base library from PIPELEXPATH)?
   - Per-workflow in an Activity (custom bundles from mthds_contents)?
   - Both (two-tier cache)?

2. **What travels with the workflow input?**
   - Today: a pre-resolved `PipeJob` with the top-level pipe object
   - Option A: send `mthds_contents` + `pipe_code` instead, resolve on worker
   - Option B: send `PipeJob` but also include `mthds_contents` for the worker to load

3. **Replay safety**
   - Library loading is I/O — it belongs in Activities, not workflow code
   - Side-effect state (loading into a singleton) is lost on replay
   - Activities re-execute cleanly on replay

4. **Caching strategy**
   - Tier 1: base library at worker startup (same for all executions)
   - Tier 2: per-request overlay cached by content hash of mthds_contents

### Key files to read and discuss

| What | Where |
|------|-------|
| Library loading (API-side) | `pipelex/pipeline/pipeline_run_setup.py` |
| Hub singleton + get_required_pipe | `pipelex/hub.py` |
| Workflow definition | `pipelex/temporal/tprl_pipe/wf_pipe_router.py` |
| Router (Temporal) | `pipelex/temporal/tprl_pipe/pipe_router_top.py` |
| Router (local, works fine) | `pipelex/pipe_run/pipe_router.py` |
| Worker startup | `pipelex/temporal/worker_cli.py` |
| All controllers that break | `pipelex/pipe_controllers/` (sequence, condition, batch, parallel, sub_pipe) |
| Library manager | `pipelex/libraries/library_manager.py` |

### When the user says "implement"

Only then shift to making code changes. Use the diagnose loop to verify each change:
1. Make code changes yourself
2. Restart the worker:
   ```bash
   tmux kill-session -t temporal-worker
   tmux new-session -d -c "$PWD" -s temporal-worker 'PIPELEXPATH=tests/integration/pipelex/pipes/controller/pipe_sequence .venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
   sleep 5
   ```
3. Run `make trund` via Bash and read the output
4. Capture worker output: `tmux capture-pane -t temporal-worker -p -S -200`
5. Repeat
