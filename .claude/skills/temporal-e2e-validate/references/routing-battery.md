# Temporal E2E — Mode 2 Step 8: routing validation battery (v1)

> Reference file for the **temporal-e2e-validate** skill — Mode 2, Step 8.
> **Run `mode-2-setup.md` first** (Steps 1–2: Temporal server + worker processes).
> The **Timeouts policy** and the **surface-results-immediately** rule in `SKILL.md` apply to every command here.
> Sibling reference files: `mode-2-tiers.md` (Steps 3–7 — Tiers 1–14), `queue-options-battery.md` (Step 9 — v2 queue options / worker-runtime profiles).

### Step 8: Routing validation battery — does `activity_queues` actually isolate workers?

This step validates the v1 per-activity, per-handle routing (PR #879) end-to-end
against a real Temporal server. It is **opt-in** — Tiers 1–11 in `mode-2-tiers.md` all run with
the default empty `activity_queues`, where every activity lands on
`worker_config.default_task_queue` and either of the split workers picks it up. Step 8
proves the routing feature works as advertised when operators actually configure
it: each activity (and, in Tier 10b, each model handle) lands on its dedicated
worker pool, never on the fallback runner.

Step 8 is **live-only** for its spend-bearing assertions. Since Part B, dry-run
also dispatches `act_*` activities (the cogt leaf mocks inside them), so routing
CAN be observed dry — but this battery predates that and its arms assert on real
provider effects (model handles, spend), so run it live as written.

**Step 8.0 — Preflight + setup**

Verify base split workers from Step 2 (`mode-2-setup.md`) are still alive (router +
runner). If not, go back and start them.

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

# Every queue named under activity_queues must have a matching
# [temporal.queue_options.<q>] entry. Empty stanza = "use worker_config
# defaults for this queue" — required by the orphan-queue validator.
[temporal.queue_options.q_inference]
[temporal.queue_options.q_handle_a]
[temporal.queue_options.q_handle_b]
[temporal.queue_options.q_image_gen]
[temporal.queue_options.q_extract]
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

Spawn the dedicated activity workers, one per named queue:

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
Step 2 (`mode-2-setup.md`) must see 0 hits for either.

```bash
timeout 600 .venv/bin/pipelex run bundle \
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
timeout 600 .venv/bin/pipelex run bundle \
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

timeout 600 .venv/bin/pipelex run bundle \
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
.venv/bin/python -c "from pathlib import Path; Path('.pipelex/pipelex_temporary_override.toml').unlink(missing_ok=True)"
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

Optionally re-run Tier 1 (default routing, `mode-2-tiers.md`) to confirm the baseline is restored.
