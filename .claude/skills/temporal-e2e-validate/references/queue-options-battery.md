# Temporal E2E — Mode 2 Step 9: queue options + worker-runtime profiles battery (v2)

> Reference file for the **temporal-e2e-validate** skill — Mode 2, Step 9.
> **Run `mode-2-setup.md` first** (Steps 1–2: Temporal server + worker processes).
> The **Timeouts policy** and the **surface-results-immediately** rule in `SKILL.md` apply to every command here.
> Sibling reference files: `mode-2-tiers.md` (Steps 3–7 — Tiers 1–14), `routing-battery.md` (Step 8 — v1 routing, the layer this battery builds on).

### Step 9: Queue options + worker-runtime profiles battery (v2)

This step validates the v2 surfaces shipped on top of v1 routing:

- **Per-queue submitter options** (`[temporal.queue_options.<q>]`) — timeouts and retry policy attach to the queue, not the activity.
- **Per-handle option overrides** (`activity_queues.*.handle_options.<handle>`) — a single handle on a queue can override the queue baseline.
- **Cluster-wide queue rate limit** (`queue_options[q].max_task_queue_activities_per_second`).
- **Named worker-runtime profiles** (`[temporal.worker_runtime_profiles.profiles.<name>]`) — concurrency slots, pollers, and rate-limit knobs become per-worker config selected via `--profile`.
- **Startup validation** — warn on unknown routing queues; fail with "did you mean?" on unknown `--task-queue`.

Scenarios A, B, D, E below are **live** for the same reason as Step 8 (`routing-battery.md`): dry-run short-circuits inference inside the workflow process, so `act_*` activities never get scheduled and the routing/timeout/rate-limit assertions are meaningless. Scenario C is a pytest/unit check and Scenario F is a CLI-startup check — neither submits a live workflow.

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

# Every queue named under activity_queues must have a matching queue_options
# entry. Empty stanza = "use worker_config defaults for this queue".
[temporal.queue_options.q_imggen]
[temporal.queue_options.q_extract]

# NOTE: q_capped (Scenario D's rate-limited queue) is intentionally NOT declared
# here. The config validator rejects a queue_options entry that no activity_queues
# route references (orphan-queue / "the overlay will never apply" error), and the
# router refuses to boot. Scenario D routes act_llm_gen_text -> q_capped in its own
# override block, so q_capped lives there, not in this base setup.

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

**Also keep a general `runner` on the default task queue.** Un-routed activities — tracing (`act_flush_trace_events`, `act_assemble_graph`) and `act_deliver` — are not in `activity_queues`, so they fall through to `default_task_queue` (`temporal_task_queue`). The specialized runners below only poll their own named queues, so without a general runner those activities have no poller and any `--graph` run (Scenarios A–B use `--graph`) **hangs** on the first trace flush (the activity sits `PENDING_SCHEDULED` forever). Spawn it:

```bash
tmux kill-session -t temporal-worker-runner 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-runner \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner'
sleep 3
tmux capture-pane -t temporal-worker-runner -p -S -20 | grep "Temporal Worker started"
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

The v2 counterpart of Tier 10a (`routing-battery.md`), but using the specialized `runner-llm` / `runner-img-gen` / `runner-extract` scopes instead of bare `runner`. Each worker only registers its own activity class, so a stray routing decision lands on the wrong queue and the activity never executes (instead of being silently picked up by a generalist runner).

Submit a pipeline that fires at least one activity of each class:

```bash
timeout 600 .venv/bin/pipelex run bundle \
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
timeout 600 .venv/bin/pipelex run bundle \
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

**Scenario C — Per-handle override wins over per-queue (pytest/unit)**

Two `act_llm_gen_text` calls (queue baseline `0:05:00`): one with a regular handle (stays at the `0:05:00` baseline), one with `claude-opus-4-7-1m` (the handle_options entry overrides to `0:25:00`). The queue is incidental — the per-handle override applies on top of whatever queue the (activity, handle) pair resolves to (here `q_llm`, since only `claude-4.6-sonnet` is routed to `q_llm_anthropic`). The reusable `per_handle_routing.mthds` bundle from Step 8 (`routing-battery.md`) can serve as a starting point if you want a live variant, but Scenario C is validated via pytest, not a live submission — inspect the `start_to_close_timeout` per scheduled activity: one should be `300s`, one should be `1500s`.

The full pytest integration sibling for this scenario already exists at:
`tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::TestSplitWorkerExtractPages::test_queue_options_start_to_close_timeout_flows_to_dispatch`.
Run that to validate the resolver layer without spinning up the live CLI:

```bash
timeout 120 .venv/bin/pytest -xvs tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::TestSplitWorkerExtractPages::test_queue_options_start_to_close_timeout_flows_to_dispatch \
  -m temporal --temporal-server local --timeout=60
```

PASS = per-queue timeout flows through the resolver into the actual dispatch. The handle-options layer is covered by the unit test below — note the class in the node ID (`TestResolveDispatch::`), which the bare function name omits:

```bash
timeout 90 .venv/bin/pytest -x -q \
  "tests/unit/pipelex/temporal/test_resolve_dispatch.py::TestResolveDispatch::test_handle_options_override_queue" \
  --timeout=60
```

**Scenario D — Queue-level rate limit observed (live)**

`max_task_queue_activities_per_second = 2` on `q_capped` is server-enforced across all pollers. Fan out ≥10 activities to `q_capped` and the server releases them at ~2/s, so the tail activities show a growing `schedule_to_start` latency.

Scenario D needs its **own** override — it routes `act_llm_gen_text` to `q_capped`, which conflicts with the base setup's `act_llm_gen_text -> q_llm`. Rewrite the override, restart the router, and run a `q_capped` worker plus the general runner (for tracing/deliver):

```bash
cat > .pipelex/pipelex_temporary_override.toml << 'EOF'
[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "q_capped"

[temporal.queue_options.q_capped]
max_task_queue_activities_per_second = 2
EOF

# kill the base-setup specialized runners (their routing no longer applies)
for s in temporal-worker-q-llm temporal-worker-q-llm-anthropic temporal-worker-q-imggen temporal-worker-q-extract; do
  tmux kill-session -t "$s" 2>/dev/null
done
# router (reads new routing) + general runner (tracing/deliver) + q_capped worker (runs the LLM activity)
tmux kill-session -t temporal-worker-router 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
tmux kill-session -t temporal-worker-runner 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-runner \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner'
tmux kill-session -t temporal-worker-q-capped 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-q-capped \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner-llm --task-queue q_capped'
sleep 5
for s in temporal-worker-router temporal-worker-runner temporal-worker-q-capped; do
  tmux capture-pane -t "$s" -p -S -15 | grep -q "Temporal Worker started" && echo "$s: started" || echo "$s: NOT started"
done
```

Reuse the existing batch bundle with a 10-item input — no need to author a bundle. `batch_temporal_describe_topics` dispatches one `act_llm_gen_text` per topic (each in its own child workflow):

```bash
cat > /tmp/batch10_inputs.json << 'EOF'
{ "topics": { "concept": "temporal_batch_test.Topic",
  "content": ["science","history","music","sports","cooking","travel","cinema","biology","economics","architecture"] } }
EOF

timeout 600 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/temporal_batch.mthds \
  --pipe batch_temporal_describe_topics \
  --inputs /tmp/batch10_inputs.json \
  --temporal --no-logo
echo "EXIT=$?"
```

Measure the throttle. The `act_llm_gen_text` activities live in **child** workflows, so aggregate scheduled→started times across all children of the run (a single `workflow show` on the root will NOT contain them). `jq`'s `fromdateiso8601` can't parse the fractional-second timestamps, so do the math in Python:

```bash
ROOT=$(temporal workflow list --limit 40 --output json | jq -r '.[] | select(.type.name=="wf_pipe_run") | .execution.workflowId' | head -1)
tmpf=$(mktemp)
for wf in $(temporal workflow list --limit 80 --output json | jq -r --arg r "$ROOT" '.[] | select(.execution.workflowId|startswith($r)) | .execution.workflowId' | sort -u); do
  temporal workflow show --workflow-id "$wf" --output json | jq -c '
    [.events[]? | select(.activityTaskScheduledEventAttributes.activityType.name=="act_llm_gen_text" and .activityTaskScheduledEventAttributes.taskQueue.name=="q_capped") | {sid:.eventId, sched:.eventTime}] as $sch
    | [.events[]? | select(.activityTaskStartedEventAttributes!=null) | {sid:(.activityTaskStartedEventAttributes.scheduledEventId), started:.eventTime}] as $st
    | $sch | map(. as $s | {sched:$s.sched, started:(($st[] | select(.sid==$s.sid) | .started) // null)}) | .[]' >> "$tmpf"
done
.venv/bin/python - "$tmpf" << 'PY'
import sys, json
from datetime import datetime
def t(s): return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
recs=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]
recs=[r for r in recs if r.get("started")]
starts=sorted(t(r["started"]) for r in recs)
lat=sorted(t(r["started"])-t(r["sched"]) for r in recs)
print(f"activities={len(recs)} started_span={starts[-1]-starts[0]:.2f}s max_schedule_to_start={lat[-1]:.2f}s")
print(f"schedule->start latencies={[round(x,1) for x in lat]}")
PY
rm -f "$tmpf"
```

PASS = `started_span` is clearly non-zero (≳4–5s for 10 activities at 2 RPS) with a growing tail latency (e.g. `[0,0,…,1,1,3]`); the initial token-bucket burst (~first 4 immediate) is expected. Don't pin exact timing — the server's rate-limit precision is per-second.

**Scenario E — Missing-worker negative (live, bounded)**

Route a real, triggerable activity to a queue nothing polls; the bounded `schedule_to_start_timeout` must make it fail fast instead of hanging forever.

> Do **not** use `act_jinja2_gen_text` here. `PipeJinja2` was renamed to `PipeCompose`, which renders templates **inline** via `render_template` (deterministic, in-process) — no pipe dispatches `act_jinja2_gen_text` anymore, so it can't be triggered from a bundle (the activity is vestigial: still registered in `tasks.py` and the `runner-jinja2` scope, but unreachable via any pipe). Use `act_llm_gen_text` and the stock `native_text_sequence` bundle instead — the objective (bounded timeout vs hang) is activity-agnostic.

```bash
cat > .pipelex/pipelex_temporary_override.toml << 'EOF'
[temporal.worker_config.activity_queues.act_llm_gen_text]
default = "q_orphan"

# q_orphan has a route (above) AND a queue_options entry (below) so it passes the
# orphan-queue validator; the schedule_to_start_timeout bounds the wait so a
# dispatch to a queue nothing polls fails fast instead of hanging. Keep it small
# (10s) — see the retry note below for why.
[temporal.queue_options.q_orphan]
schedule_to_start_timeout = "0:00:10"
EOF

# router reads the new routing; keep a general runner up but start NO q_orphan worker
tmux kill-session -t temporal-worker-router 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
tmux has-session -t temporal-worker-runner 2>/dev/null || tmux new-session -d -c "$PWD" -s temporal-worker-runner \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner'
sleep 4
pgrep -fl "q_orphan" >/dev/null && echo "WARNING: a worker polls q_orphan" || echo "confirmed: nothing polls q_orphan"

timeout 120 .venv/bin/pipelex run bundle \
  tests/integration/pipelex/temporal/library_crate/native_text_sequence.mthds \
  --pipe native_text_sequence \
  --temporal --no-logo
echo "EXIT=$?"
```

Expected: non-zero exit with `activity ScheduleToStart timeout` in the message. Confirm in workflow history that the scheduled `act_llm_gen_text` event on `q_orphan` carries `scheduleToStartTimeout=10s` and fails with `TIMEOUT_TYPE_SCHEDULE_TO_START`:

```bash
WF=$(temporal workflow list --limit 20 --output json | jq -r '.[] | select(.type.name=="wf_pipe_router") | .execution.workflowId' | grep step_one | head -1)
temporal workflow show --workflow-id "$WF" --output json \
  | jq -r '.events[]? | select(.activityTaskScheduledEventAttributes.activityType.name=="act_llm_gen_text") | "taskQueue=\(.activityTaskScheduledEventAttributes.taskQueue.name) s2s=\(.activityTaskScheduledEventAttributes.scheduleToStartTimeout)"'
temporal workflow show --workflow-id "$WF" --output json \
  | jq -r '.events[]? | .activityTaskTimedOutEventAttributes.failure.timeoutFailureInfo.timeoutType // empty'
```

PASS = bounded timeout, clear error. **Note on total time:** each pipe step runs as a child workflow that **retries on failure** (≈3 attempts), so the run takes ≈`maxAttempts × schedule_to_start` (≈30s at a 10s bound), not a single bound — that's why the bound is kept small. It is still bounded; the point is "fails fast per attempt, no infinite hang." FAIL = the run exceeds `maxAttempts × bound` substantially (true hang) or the error is an unclear wrapper with no `ScheduleToStart`.

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

Sanity-check that a **known** queue is accepted by the validator. Target `temporal_task_queue` (the `default_task_queue`) — it is always known regardless of which scenario's override is currently loaded. Do **not** use `q_llm` here: each scenario's override is written with `cat >` (full replace), so by this point the active override is Scenario E's, which declares only `q_orphan` — `q_llm` would be (correctly) rejected as unknown.

```bash
OUT=$(timeout 60 .venv/bin/python -m pipelex.temporal.worker_cli \
  --task-queue temporal_task_queue --is-unit-testing 2>&1); RC=$?
if echo "$OUT" | grep -q "WorkerTaskQueueUnknownError"; then
  echo "Scenario F sanity FAIL — known queue 'temporal_task_queue' wrongly rejected by the task-queue validator"
else
  echo "Scenario F sanity PASS — 'temporal_task_queue' passed the task-queue validator (no WorkerTaskQueueUnknownError; rc=$RC)"
fi
```

PASS = no `WorkerTaskQueueUnknownError` — the run proceeds *past* the task-queue validator, which runs early (`worker_cli.py`, before library load and `Worker(...)` construction) and only guards the `--task-queue` name; it does **not** boot a worker by itself.

> Note: under `--is-unit-testing` the run then dies on an unrelated `RuntimeError: Failed validating workflow <test-only workflow>` (the exact one varies, e.g. `wf_test_content_generator_child` or `wf_test_structured_output_cross_process`) — temporalio sandbox validation of a test-only workflow, queue-name-independent and orthogonal to this check. (If that test-workflow issue is ever fixed, the known queue boots a real polling worker instead and the `timeout 60` fires at `rc=124`.) Either outcome is "past the validator" and PASSES; only `WorkerTaskQueueUnknownError` is a Scenario F failure. The sandbox-validation issue is tracked as a product follow-up in `wip/temporal-e2e-validate-skill.md`.

**Step 9.t — Teardown**

```bash
.venv/bin/python -c "from pathlib import Path; Path('.pipelex/pipelex_temporary_override.toml').unlink(missing_ok=True)"
rm -f /tmp/batch10_inputs.json
for q in q-llm q-llm-anthropic q-imggen q-extract q-capped; do
  tmux kill-session -t "temporal-worker-$q" 2>/dev/null
done
tmux kill-session -t temporal-worker-runner 2>/dev/null
tmux kill-session -t temporal-worker-router 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
tmux new-session -d -c "$PWD" -s temporal-worker-runner \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope runner'
sleep 4
tmux capture-pane -t temporal-worker-router -p -S -10 | grep "Temporal Worker started"
```
