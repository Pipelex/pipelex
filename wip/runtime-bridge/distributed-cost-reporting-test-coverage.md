# Cost reporting in distributed (split-worker) mode — test-coverage audit

**Status:** ✅ **RESOLVED — coverage added.** The prioritized additions below were implemented and are green. See "Resolution (as-built)" for the exact files and the decisions taken. The audit body is retained as the code-grounded map and rationale.
**Source:** Audit triggered during `/temporal-e2e-validate` (full Mode 2 run on `feature/Runtime-bridge-extraction`). Question asked: *do we have comprehensive testing of cost reporting in distributed mode with real inference — emission and aggregation — and what should we add?*
**Scope:** the token-usage → cost-report path when inference runs on a **separate Temporal `runner` worker process** (split-worker topology), with **real** provider inference. Touches `pipelex/reporting/`, `pipelex/tracing/`, `pipelex/cogt/usage/`, `pipelex/temporal/tprl_pipe/`, and the test tree under `tests/`.

---

## Resolution (as-built)

All four audit questions now have automated coverage. No production code changed — these are characterization/regression tests plus one test-helper extension and a skill upgrade. **R2 decision: keep accepting** the activity-retry over-count (matches the existing documented stance); it is now regression-visible at the cost-total level rather than fixed.

**Capture (stage 1 — the biggest blind spot, real-provider branch previously asserted nowhere):**

- `tests/unit/pipelex/plugins/openai/test_openai_completions_usage_capture.py` — factory mapping (incl. cached/audio/reasoning/prediction detail fields) + `_gen_text` worker wiring reads `response.usage` into `nb_tokens_by_category`; plus the no-`usage` case pinned (stays empty → the documented silent zero-token emit).
- `tests/unit/pipelex/plugins/openai/test_openai_responses_usage_capture.py` — same for the Responses API.
- `tests/unit/pipelex/plugins/openai/test_openai_img_gen_worker_usage_capture.py` — `_gen_image_list` reads `ImagesResponse.usage`.
- `tests/unit/pipelex/cogt/extract/test_extract_worker_usage_capture.py` — extract page-count fallback, both directions (fills when provider reports none; not overridden when provider sets usage).

**Aggregate + non-LLM (stage 3, the discriminated-union wire concern):**

- `tests/unit/pipelex/tracing/test_non_llm_usage_aggregation.py` — img-gen/extract/search usage JSON-round-trip through `UsageReportEvent` (discriminator intact) → `UsageAggregator.aggregate` → `CostRegistry.aggregate_costs` with exact per-type totals.
- `tests/unit/pipelex/reporting/test_emit_runner_fallback_non_llm.py` — the previously-untested `_report_img_gen_job` / `_report_extract_job` dispatch branches emit through the real runner fallback to NDJSON and read back as the right concrete type.

**Distributed (split-worker) summed totals + cross-child + R2:**

- `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` — added `test_runner_usage_sums_to_expected_cost_total` (summed total via `aggregate_costs`, computed independently from the cross-worker events — no longer just landing/dedup/passthrough).
- `tests/integration/pipelex/temporal/tracing/test_split_worker_cross_child_usage.py` — PipeParallel fan-out: usage from ≥2 distinct child workflows aggregates into one parent total over the shared `pipeline_run_id` partition.
- `tests/unit/pipelex/reporting/test_emit_runner_fallback.py` — added `test_retried_activity_double_counts_cost_total_documenting_r2` pinning R2 at the billing level (retry → doubled tokens/cost). Flip these assertions if the idempotent-resequence fix ever lands.

**E2E (real inference, gated/opt-in — the thing that was invisible):**

- `tests/integration/pipelex/temporal/tracing/test_split_worker_real_inference_cost.py` — marked `inference`/`llm` (default lanes deselect it; passes when run). Real `llm_gen_text` runs on the runner queue with the context cache cleared, so real provider tokens are captured → runner fallback → aggregated to a non-zero total with a real model handle. Enabled by a backward-compatible `runner_act_llm_gen_text` param on `make_split_workers` in `helpers.py`.

**`/temporal-e2e-validate` skill — manual eyeball → numeric assertion:**

- `.claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py` — sums input/output tokens straight from the NDJSON usage events, checks event count + `act_*` fallback + optional un-truncated CSV cross-check, and asserts model-type / non-zero. Wired into Tier 8b (`references/mode-2-tiers.md`) for the mock, cross-child, live, and img-gen/extract-live arms.

**Deferred / accepted (unchanged by design):**

- **R2 over-count** — accepted; pinned, not fixed (decision above).
- **Zero-token silent emit** — capture side pinned (no-`usage` → empty); the downstream zero-token `UsageReportEvent` emission remains accepted behavior.
- **Best-effort drops** — unchanged; the existing `_emit_best_effort` / child-flush WARNING-and-drop behavior is by design and already has gating tests.
- **Non-LLM full Temporal activity hop** — the runner-fallback emit path is type-agnostic (proven for LLM via the split-worker tests) and non-LLM usage is covered at the `ReportingManager`/aggregator level + the skill's live arm; a dedicated split-worker bundle with fake img-gen/extract activities was judged redundant.

---

## Context for a cold-start session

Read this first if you're picking this up cold to write the detailed plan.

**Why this matters now.** The runtime-bridge work makes Pipelex pipes runnable from inside a host's own Temporal activities, and the hosted platform runs Pipelex on Temporal with **split workers** — a `router` process runs the workflows, a `runner` process runs the inference activities. Cost reporting (token usage → priced cost table / `cost_report` JSON) is a billing-adjacent surface. In split-worker mode the usage numbers are produced on one process (the runner, where inference happens) and assembled on another (the router/submitter). That cross-process assembly is the thing under audit.

**The cost path has three stages — keep them distinct when planning.**

1. **Capture** — inside the inference activity on the runner, read the provider response's token counts into `LLMJob.llm_tokens_usage.nb_tokens_by_category` (and the img-gen / extract / search equivalents).
2. **Emit** — turn that into a `UsageReportEvent` and persist it to the trace partition. In split-worker mode the runner has no registered event-log context, so emission goes through the **runner fallback** (`writer_id = act_{pid}_{uuid8}`, written to a `wf_*__w_act_*.ndjson` file or the DynamoDB partition).
3. **Aggregate + render** — the parent `WfPipeRun` runs `act_assemble_tracing` (with `assemble_usage=True`), which reads *every* event in the `pipeline_run_id` partition (router + all runners + all child workflows), passes them through `UsageAggregator.aggregate` → `PipeOutput.tokens_usages`, and the submitter prices and renders the cost table.

**The one-line finding.** Stages 2 and 3 are correct-by-construction and well unit-tested **in isolation / direct mode**. What is **not** tested anywhere by assertion is: (a) stage 1 with a *real* provider response, (b) the *summed total* end-to-end in distributed mode, (c) cross-child fan-out summation, and (d) any non-LLM usage (img-gen / extract / search). Real-inference distributed cost is exercised **only manually** via this skill's Tier 8b "live arm", which just eyeballs that a table rendered.

**Two things that are real bugs, not just missing tests** — see "Correctness risks" below. R2 (activity-retry over-count) is already documented and test-pinned as *current accepted behavior*; the planning session should decide whether to fix it or keep accepting it.

**How to use this doc.** The "How the path works" section is the map (with file:line anchors). "What is / isn't tested" is the gap inventory. "Prioritized additions" is a menu, not a committed plan — the planning session should sequence it and decide the R2 question. Nothing here has been implemented.

---

## TL;DR — the four questions, answered

- **Comprehensive testing of distributed real-inference cost reporting?** No. Zero automated tests run real inference through split workers and assert the cost numbers. Only manual eyeballing (skill Tier 8b live arm).
- **Do we correctly emit usage event logs?** For LLM: the emission plumbing is correct and well-tested, but the **real-capture branch is asserted by nothing** — mock-inference diverges from real *before* the worker is built, so a passing mock test does not prove real provider tokens are read. For img-gen / extract / search: emission is **untested in any mode**.
- **Do we correctly aggregate them?** The aggregator + cost registry are correct and have exact-total unit tests — **but only in no-temporal/direct mode**. In distributed mode no test asserts a summed total (only "events land / no per-node dup / 1:1 passthrough"). Cross-child aggregation has **zero** automated assertions.
- **What to add?** Real-provider capture unit tests; split-worker summed-total + cross-child + non-LLM integration tests; one gated real-inference e2e; and turn the skill's manual Tier 8b into a numeric assertion. Details below.

---

## How the path works (code-grounded map)

### Capture (runner process, inside the activity)

`LLMJob.llm_tokens_usage.nb_tokens_by_category` is seeded empty in `llm_job_before_start` (`pipelex/cogt/llm/llm_job.py:36-42`), then populated from the provider response inside the plugin worker:

- OpenAI completions / gateway / Portkey (gateway subclasses completions — `gateway_completions_factory.py:39`): `openai_completions_llm_worker.py:201-202` (text), `:266-267` (object); mapping in `openai_completions_factory.py:101-111` (`usage.prompt_tokens`, `usage.completion_tokens`, cached/reasoning details).
- OpenAI responses API: `openai_responses_llm_worker.py:179-180`; factory `openai_responses_factory.py:100-106`.
- Google: `google_llm_worker.py:236-237, 313-325`; factory `google_factory.py:144-162`.
- Bedrock: `bedrock_llm_worker.py:85-86`.
- Img-gen: `openai_img_gen_worker.py:134, 149-150, 164`; reported at `img_gen_worker_abstract.py:69-70 / 108-110`.
- Extract: provider sets `nb_tokens_by_category`, else a page-count fallback fills it (`extract_worker_abstract.py:96-101`); reported at `:105-106`.
- Search: hardcoded (`linkup_search_worker.py:90, 154`); reported at `search_worker_abstract.py:49, 72`.

All of this runs synchronously inside the activity on the runner process, so the populated `tokens_usage` is what the runner-side fallback emits.

**Mock diverges before capture.** `llm_gen_text` short-circuits to the mock helper at the top (`pipelex/cogt/content_generation/llm_generate.py:14-15`; object/list at `:29-30`, `:50-51`) — it never builds an `LLMJob`, never gets a worker, never reads a provider response. Mock and real **re-converge only at `report_inference_job`** (the *emit* half). The mock helper hand-builds synthetic usage `MOCK_INFERENCE_NB_TOKENS_BY_CATEGORY = {INPUT: 100, OUTPUT: 50}` (`dry_mock.py:58-61, 94-108`). **Consequence: mock passing proves emit/aggregate, not capture.** And img-gen / extract leaves *raise* `MockInferenceUnsupportedError` under mock (`img_gen_generate.py:12-13`, `extract_generate.py:11-13`) — so mock cannot cover them at all.

### Emit (runner fallback)

`ReportingManager.report_inference_job` → `_emit_usage_event` (`pipelex/reporting/reporting_manager.py:149-185`):

```python
if not trace_context.emit_usage_events: return        # :173 — the --costs gate, before context lookup
context = self._event_log_contexts.get(trace_context.lookup_key)   # :176
if context is not None:
    self._emit_via_registered_context(...)            # FAST PATH, writer_id="primary"
    return                                            # :179 — hard return
self._emit_usage_event_runner_fallback(...)           # FALLBACK, writer_id="act_*"
```

On the runner, `_event_log_contexts` is empty (`set_event_log` is only ever called on the router — `wf_pipe_router.py:114-120`), so the fallback always wins. `writer_id` is generated once per process under a double-checked lock in `ActivityEventLogCache.get_or_create` as `f"act_{os.getpid()}_{uuid4().hex[:8]}"` (`activity_event_log.py:64-76`), and the one-shot WARNING "Runner-side usage event emission engaged" comes from `activity_event_log.py:93-99`. Event type: `UsageReportEvent` (`pipelex/tracing/trace_events.py:162-167`), carrying `tokens_usage: AnyTokensUsage` + a top-level `writer_id`.

### Aggregate + render (parent / submitter)

`act_assemble_tracing` (`pipelex/temporal/tprl_pipe/act_assemble_tracing.py:36-50`) → `assemble_tracing` (`pipelex/pipe_run/tracing_assembly.py:50-131`):

- Reads events **once**, keyed by `pipeline_run_id` only (`:95-99`). The NDJSON read globs **every** `*.ndjson` in `{traces_dir}/{pipeline_run_id}/` (`ndjson_event_log.py:133`), so router `wf_*.ndjson` and all runner `wf_*__w_act_*.ndjson` files are picked up by the same glob. Read-side dedup key: `(workflow_id, writer_id, type(event).__name__, sequence)` (`ndjson_event_log.py:150`); DynamoDB equivalent `SK = EVENT#{workflow_id}#{writer_id}#{sequence:010d}` overwrites idempotently (`dynamodb_event_log.py:99-118`). This is what makes Temporal **replay** safe.
- `if assemble_usage: result.tokens_usages = UsageAggregator.aggregate(events)` (`:112-113`). `UsageAggregator.aggregate` is a 1:1 passthrough — `[evt.tokens_usage for evt in events if isinstance(evt, UsageReportEvent)]` (`usage_aggregator.py:12-22`), **no dedup/grouping of its own** (dedup already happened in `read_events`).
- `TracingAssembly` rides back; `wf_pipe_run.py:91-114` copies `tokens_usages` onto `PipeOutput.tokens_usages` (`pipe_output.py:32`).
- Render: `cost_report_renderer.py:21-82` (called from `_run_core.py:320-324`); per-model grouping + pricing in `cost_registry.py:216-279`; price comes from `tokens_usage.unit_costs` captured at inference time, **not** re-priced from a catalog (`costs_per_token.py:4-31`). Suppression: `has_reportable_usage` = `total_nb_tokens > 0 or total_cost > 0` (`cost_registry.py:41-49`), so dry-run (zero) is suppressed; a real run on a free model still reports (tokens > 0, cost 0).

### Cross-child fan-out

Join is **by `pipeline_run_id` on a shared partition** — there is no per-workflow join. Each child gets a distinct `workflow_id` (`temporal_pipe_router.py:69`) but the **same `pipeline_run_id`** (`TraceContext.copy_for_child` preserves it — `trace_context.py:66-84`; the fallback stamps it from the job metadata — `reporting_manager.py:270`). Only the top-level `WfPipeRun` runs `act_assemble_tracing`, and its single `read_events(pipeline_run_id)` sweeps the whole partition. Load-bearing invariant: every child's `pipeline_run_id` must equal the parent's, and (NDJSON backend) `traces_dir` must be shared across all hosts — the hosted platform must use the DynamoDB backend for multi-host (`ndjson_event_log.py:38-40`).

---

## What is tested vs what only "runs without crashing"

### Distributed (true split-worker) topology

Only `tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py` runs a real two-queue split — and it **substitutes** `act_llm_gen_text` with a helper that hand-builds `LLMTokensUsage` (INPUT=1, OUTPUT=1) (`helpers.py:195-246`). So even here there is no real worker and no provider read. It asserts:

- an `act_*` usage event **lands** in a runner file (`test_runner_usage_event_lands_in_same_ndjson_dir`),
- exactly **one** event per `(node_id, workflow_id)` — fast-path/fallback de-dup (`test_no_double_emit_in_split_worker_pool`),
- the aggregator returns one record per event, **none dropped, order preserved** (`test_runner_usage_aggregates_to_tokens_usages` → `tokens_usages == [evt.tokens_usage for evt in usage_events]`).

None of them sums tokens or asserts `total == N×{input,output}`.

### Numeric correctness — exists, but only no-temporal

Exact-total assertions live entirely outside Temporal, on hand-built usage:

- `tests/unit/pipelex/cogt/usage/test_cost_registry.py` — per-model groupby totals, `compute_total_cost==3.5`, `aggregate_costs` exact `total_cost==0.2` / `total_nb_tokens==150`, cached/non-cached splits. Richest numeric coverage.
- `tests/unit/pipelex/reporting/test_cost_report_renderer.py` — free model `total_cost==0.0 / 150`, console `total_cost==0.2`.
- `tests/integration/pipelex/pipeline/test_cost_report_rendering.py` — rendered string contains `"0.2000"` (DIRECT).
- `tests/unit/pipelex/reporting/test_reporting_event_emission.py` — single emitted event has `nb_tokens_by_category[INPUT]==100` (fast path, in-memory log).

### Mock-inference (synthetic tokens, emit-path only)

- `test_mock_inference_temporal.py` — real `act_llm_gen_text` with `is_mock_inference=True`, but **single task queue** (not split-worker), so it doesn't even hit the runner fallback. Asserts `tokens_usages` reportable under the sentinel `mock_inference` model; no exact total.
- `test_mock_inference_direct.py` — DIRECT; asserts non-None / `has_reportable_usage`; no exact total.

### Graph-only / serialization-only (zero cost assertions despite real cross-child fan-out)

- `test_wf_graph_tracing_batch.py`, `test_wf_graph_tracing_parallel.py` — real fan-out to child workflows, **dry-run**, assert only GraphSpec structure (node statuses, BATCH/CONTAINS/DATA edges, multiple NDJSON files). Never touch `tokens_usages`.
- `test_split_worker_object_gen.py`, `test_split_worker_extract_pages.py` — in-process single worker; assert serialization / activity-id dispatch; **no usage/cost assertion**.

### Precise answers

- **A. Exact aggregated total in split-worker mode (even mock)?** No. The three split-worker tests assert landing / per-node de-dup / 1:1 passthrough, never a summed total.
- **B. Real-inference cost correctness in distributed mode?** No automated test. Only manual via the skill's Tier 8b live arm ("expect a table with the real model handle and real token counts") — eyeball, no assertion.
- **C. Cross-child sum → single parent total?** No automated assertion, mock or real. The fan-out tracing tests are graph-only/dry-run; the skill's "A+B+C → one report" block is manual.
- **D. Img-gen / extract / search usage in distributed mode?** Zero coverage in **any** mode. Grep for `ImgGenTokensUsage` / `ExtractTokensUsage` / `SearchTokensUsage` across `tests/` returns nothing; every usage test uses `LLMTokensUsage` only.
- **E. Fast-path vs fallback de-dup?** Covered by `test_no_double_emit_in_split_worker_pool` (buckets by `(node_id, workflow_id)`, asserts count==1 per key) plus unit gating tests. It does **not** assert token totals and does **not** cover the retry over-count (R2 below).

---

## Correctness risks (real bugs, not just missing tests)

- **R2 — activity-retry over-count.** A Temporal-**retried** activity (not replay) re-emits the same inference's usage at sequence N+1 instead of overwriting N, defeating the `(workflow_id, writer_id, sequence)` dedup → counted twice. Documented at `docs/.../tracing-cost-reporting.md:51`, pinned as *current accepted behavior* by `tests/unit/pipelex/reporting/test_emit_runner_fallback.py:367-388` (asserts two events at sequences `[0,1]`). The `strict_mode` / idempotent-resequence fix is deferred. With M children doing retryable inference, the over-count probability scales with fan-out × retry rate. **The planning session must decide: fix or keep accepting.**
- **Zero-token silent emit.** If a provider returns no `usage`, the worker skips the assignment (`and (usage := response.usage)` guards everywhere, e.g. `openai_completions_llm_worker.py:201`), but the job still has a truthy `LLMTokensUsage`, so `_report_llm_job` does not hit its `if not llm_tokens_usage` guard (`reporting_manager.py:116`) — a `UsageReportEvent` is emitted **with zero tokens**. Silent under-count, no flag.
- **Best-effort drops.** Emit (`_emit_best_effort`, `reporting_manager.py:208-221`) and child flush (`wf_pipe_router.py:175-177`) swallow infra failures with a WARNING; an unwritable dir / DDB reject / unshared NDJSON `traces_dir` across hosts silently drops a slice. The run still succeeds; the report is quietly short. A whole-read failure is at least visible (`usage_assembly_error` → `tokens_usages=None` → no report), but per-line/per-file drops are not.

The aggregator and renderer themselves are lossless — all risk lives in the capture/emit/persist/read layer.

---

## Prioritized additions (the original menu — now implemented; see "Resolution (as-built)" above for the landed files)

### Unit — cheapest, closes the biggest blind spot (real capture)

- **Real-provider capture tests.** Substitute the OpenAI/gateway client with a canned response carrying `usage.input_tokens=…` (and the cached/reasoning detail fields); assert `nb_tokens_by_category` is populated correctly. One each for completions, responses API, **img-gen, extract**. Deterministic, no spend — this is the single highest-value gap, since the real-capture branch is asserted nowhere today.
- **No-`usage` provider case.** Decide intended behavior (today: silent zero-token emit) and pin it.
- **Non-LLM through the aggregator.** A test routing `ImgGenTokensUsage` / `ExtractTokensUsage` / `SearchTokensUsage` through `UsageReportEvent → aggregate_costs` and asserting the per-type total (currently never exercised).

### Integration — split-worker, fixture/mock (no spend)

- **Summed-total assertion.** Extend `test_split_worker_usage.py`: inject known synthetic per-call tokens, assert `aggregate_costs(tokens_usages).total_nb_tokens == expected sum` (not just landing/dedup/passthrough).
- **Cross-child sum.** PipeBatch/PipeParallel split-worker test where each child emits known usage; assert the parent's single total = sum across children. Highest-risk uncovered path (also the natural home for an R2 regression).
- **Non-LLM cross-worker.** Split-worker img-gen + extract usage crossing the runner fallback via a fixture worker returning canned `ImgGenTokensUsage` / `ExtractTokensUsage`; assert aggregate + render. Closes D in distributed mode.
- **R2 at the total level.** Force an activity retry and assert the cost total double-counts — make the known over-count regression-visible (and, if fixed, flip the assertion).

### E2E — real inference, gated/opt-in lane

- One marked real-inference split-worker test: assert `tokens_usages` non-empty, every entry non-zero, model handles match the real models, usage-record count == number of inference calls, total > 0. Even loose bounds catch the entire "real provider usage not captured/emitted/aggregated in distributed mode" class — the exact thing that's invisible today (and that I could not verify by eyeball this session because the live cost tables were column-truncated).

### temporal-e2e-validate skill — make the manual check assert

- Strengthen Tier 8b's live arm: parse the NDJSON usage events and assert **summed input/output across all `__w_act_*` files == rendered table total**, and usage-event count == inference-call count. Dump costs to CSV (un-truncated) so real non-zero numbers are actually visible — the current terminal table truncates to `0 … …`, making the eyeball check nearly worthless.
- Add an img-gen / extract live cross-worker **cost** assertion (Tiers 4/5/10c run those live but never check the numbers).

---

## Key files

- Capture: `pipelex/cogt/content_generation/llm_generate.py`, `dry_mock.py`, `img_gen_generate.py`, `extract_generate.py`; `pipelex/cogt/llm/llm_job.py`, `llm_worker_abstract.py`; `pipelex/plugins/openai/openai_completions_llm_worker.py` (+ `openai_completions_factory.py`, `openai_responses_factory.py`), `pipelex/plugins/openai/openai_img_gen_worker.py`; `pipelex/cogt/extract/extract_worker_abstract.py`.
- Emit: `pipelex/reporting/reporting_manager.py`, `pipelex/tracing/activity_event_log.py`, `pipelex/tracing/trace_events.py`.
- Aggregate + render: `pipelex/temporal/tprl_pipe/act_assemble_tracing.py`, `pipelex/pipe_run/tracing_assembly.py`, `pipelex/tracing/usage_aggregator.py`, `pipelex/tracing/ndjson_event_log.py`, `pipelex/tracing/dynamodb_event_log.py`, `pipelex/cogt/usage/cost_registry.py`, `pipelex/cogt/usage/costs_per_token.py`, `pipelex/reporting/cost_report_renderer.py`, `pipelex/core/pipes/pipe_output.py`.
- Tests today: `tests/integration/pipelex/temporal/tracing/{test_split_worker_usage.py,test_mock_inference_temporal.py,test_split_worker_object_gen.py,test_split_worker_extract_pages.py,helpers.py}`; `tests/unit/pipelex/reporting/{test_emit_runner_fallback.py,test_emit_usage_event_gating.py,test_reporting_event_emission.py,test_cost_report_renderer.py}`; `tests/unit/pipelex/cogt/usage/test_cost_registry.py`; `tests/unit/pipelex/tracing/{test_usage_aggregator.py,test_writer_id_schema.py,test_trace_events.py}`; `tests/unit/pipelex/pipe_run/test_tracing_assembly.py`.

## Related

- [`cost-reporting-validation-prompts.md`](cost-reporting-validation-prompts.md) — operator cheat-sheet of `/temporal-e2e-validate` prompts that drive the Tier 8b arms this audit motivated.
- `../observer-and-telemetry/` — sibling tracing/telemetry follow-ups.
- `docs/.../tracing-cost-reporting.md` (R2 documentation) and the `wip/registry/cost-report-deferred-decisions.md` deferred items (e.g. `tracing_config.is_enabled=false` + `--costs` → silent no-report).
- This audit was produced cross-checking three independent code sweeps (emission, aggregation, test inventory); the file:line anchors above are the load-bearing evidence — re-verify any that look stale before building on them.
