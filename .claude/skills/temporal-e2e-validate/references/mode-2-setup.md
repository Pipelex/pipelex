# Temporal E2E — Mode 2 setup: server + worker processes

> Reference file for the **temporal-e2e-validate** skill — Mode 2, Steps 1–2. **Read this first** before any other Mode 2 reference.
> The **Timeouts policy** and the **surface-results-immediately** rule in `SKILL.md` apply to every command here.
>
> Mode 2 reference files (read as the work requires):
>
> - `mode-2-setup.md` — Steps 1–2: Temporal server + worker processes (this file)
> - `mode-2-tiers.md` — Steps 3–7: Tiers 1–14, graph, isolation, codec, final report
> - `routing-battery.md` — Step 8: v1 `activity_queues` routing battery
> - `queue-options-battery.md` — Step 9: v2 queue options + worker-runtime profiles

## Why Mode 2: True 3-Process Validation

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

Same as Mode 1 Step 1 in `SKILL.md` — start `temporal server start-dev` in a `temporal-server` tmux session if `curl -s http://localhost:8233` shows it is not already up.

**Search-attribute registration on a fresh dev server.** Worker boot performs a
hard-fail audit (`check_required_search_attributes`) and refuses to start if any
of the Pipelex custom attributes (defined in `BUILTIN_SEARCH_ATTRIBUTES`) is
missing from the namespace. The error message includes the exact
`pipelex setup-temporal-namespace` command to run. For a freshly started
`temporal server start-dev`, register them once (idempotent):

```bash
.venv/bin/pipelex setup-temporal-namespace
```

This wraps the same helper the test conftest uses, so the set stays in sync
with `BUILTIN_SEARCH_ATTRIBUTES` automatically. (If you need to invoke the raw
Temporal CLI for some reason — e.g. an environment where the Pipelex CLI is
unavailable — the command shape is
`temporal operator search-attribute create --namespace <ns> --name <Name> --type Keyword`,
one per attribute name from `BUILTIN_SEARCH_ATTRIBUTES`.)

Mode 1 (pytest) handles this automatically via the test conftest. Mode 2 needs
it done before worker startup.

### Step 2: Start the worker processes

The workers should NOT have test bundles in their PIPELEXPATH — the whole point is
that bundles arrive via the LibraryCrate in the PipeJob.

**Two scoped workers (cross-process regression setup — recommended).**
Splits responsibilities so workflows and activities run in different processes:
- `router` worker registers all workflows (`WfPipeRouter`, `WfPipeRun`, …),
  `disable_all_activities = true`.
- `runner` worker registers all activities (`act_deliver`, `act_llm_*`,
  `act_assemble_tracing`, `act_flush_trace_events`, …), `disable_all_workflows = true`.

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
> - Activities the runner actually executes in dry-run (`act_assemble_tracing`,
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
# Bounded wait: fail fast with captured logs if a worker can't start within 30s
# (boot is normally <5s — anything past that means a stuck config validator,
# missing search attributes, or the worker crashed early).
for session in temporal-worker-router temporal-worker-runner; do
  for attempt in $(seq 1 30); do
    if tmux capture-pane -t "$session" -p 2>/dev/null | grep -q "Temporal Worker started"; then break; fi
    if [ "$attempt" -eq 30 ]; then
      echo "TIMEOUT: $session did not report 'Temporal Worker started' within 30s — last 50 lines:"
      tmux capture-pane -t "$session" -p -S -50
      exit 1
    fi
    sleep 1
  done
done
tmux capture-pane -t temporal-worker-router -p -S -30 | grep -E "scope|started for|search-attribute" | head -5
tmux capture-pane -t temporal-worker-runner -p -S -30 | grep -E "scope|started for|search-attribute" | head -5
```

Look for `Temporal Worker started for 'temporal_task_queue'` in each session, plus
`profile='default' scope='router'` and `'runner'` respectively. If a worker fails with
`SearchAttributeRegistrationError`, register the missing attributes per Step 1 and
restart the worker — do **not** bump the timeout and retry blind.

**Alternative — single full worker** (simpler, but masks distributed-execution bugs;
use only when you don't need the regression coverage):

```bash
tmux has-session -t temporal-worker 2>/dev/null && tmux kill-session -t temporal-worker
tmux new-session -d -c "$PWD" -s temporal-worker \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed'
# Bounded wait: fail fast with captured logs if the worker can't start within 30s
for attempt in $(seq 1 30); do
  if tmux capture-pane -t temporal-worker -p 2>/dev/null | grep -q "Temporal Worker started"; then break; fi
  if [ "$attempt" -eq 30 ]; then
    echo "TIMEOUT: temporal-worker did not report 'Temporal Worker started' within 30s — last 50 lines:"
    tmux capture-pane -t temporal-worker -p -S -50
    exit 1
  fi
  sleep 1
done
tmux capture-pane -t temporal-worker -p -S -30
```

When using two scoped workers, replace any later capture commands like
`tmux capture-pane -t temporal-worker ...` with the appropriate session name
(`temporal-worker-router` or `temporal-worker-runner`).
