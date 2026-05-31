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

All scenarios A-D below are **live-only** for the same reason as Step 8 (`routing-battery.md`): dry-run short-circuits inference inside the workflow process, so `act_*` activities never get scheduled and the routing/timeout/rate-limit assertions are meaningless.

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

**Scenario C — Per-handle override wins over per-queue (live)**

Two LLM calls routed to `q_llm_anthropic`: one with a regular Anthropic handle (uses queue baseline `0:05:00`), one with `claude-opus-4-7-1m` (the handle_options entry overrides to `0:25:00`). The reusable `per_handle_routing.mthds` bundle from Step 8 (`routing-battery.md`) can serve here, but with a manual pipe definition where step 2 uses model `"claude-opus-4-7-1m"` — adapt or write a new bundle. For now, validate via the per-queue value flowing as in Scenario B, plus inspect the `start_to_close_timeout` per scheduled activity in history: one should be `300s`, one should be `1500s`.

The full pytest integration sibling for this scenario already exists at:
`tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::test_queue_options_start_to_close_timeout_flows_to_dispatch`.
Run that to validate the resolver layer without spinning up the live CLI:

```bash
timeout 120 .venv/bin/pytest -xvs tests/integration/pipelex/temporal/tracing/test_split_worker_extract_pages.py::TestSplitWorkerExtractPages::test_queue_options_start_to_close_timeout_flows_to_dispatch \
  -m temporal --temporal-server local --timeout=60
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

# q_orphan must have a queue_options entry to pass the orphan-queue validator;
# the schedule_to_start_timeout bounds the wait so a workflow dispatched to a
# queue nothing polls fails fast instead of hanging.
[temporal.queue_options.q_orphan]
schedule_to_start_timeout = "0:00:30"
EOF
```

Restart the router (re-read the override), then submit a pipeline that fires `act_jinja2_gen_text`. With Phase 4's strict CLI validation, the worker process would refuse to start on `--task-queue q_orphan` if you tried — but a routing-only orphan queue (referenced in `activity_queues` with a `queue_options` entry but polled by no worker) is fine until dispatch.

After submission, the workflow's first `act_jinja2_gen_text` invocation will time out on `schedule_to_start` thanks to the bound set above. Expected: the workflow fails with a clear `schedule_to_start` timeout, not a hang.

```bash
timeout 600 .venv/bin/pipelex run bundle \
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
.venv/bin/python -c "from pathlib import Path; Path('.pipelex/pipelex_temporary_override.toml').unlink(missing_ok=True)"
for q in q-llm q-llm-anthropic q-imggen q-extract; do
  tmux kill-session -t "temporal-worker-$q" 2>/dev/null
done
tmux kill-session -t temporal-worker-router 2>/dev/null
tmux new-session -d -c "$PWD" -s temporal-worker-router \
  '.venv/bin/python -m pipelex.temporal.worker_cli --is-not-sandboxed --scope router'
sleep 4
tmux capture-pane -t temporal-worker-router -p -S -10 | grep "Temporal Worker started"
```
