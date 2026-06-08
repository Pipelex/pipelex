# Cost-reporting test additions — two cleanup follow-ups

**Status:** 🧹 Optional cleanups, no correctness impact. Surfaced by a code review of the distributed-cost-reporting test additions (see [`distributed-cost-reporting-test-coverage.md`](distributed-cost-reporting-test-coverage.md), "Resolution (as-built)"). The review found **no bugs**; these are cosmetic dead-code / weak-assertion items safe to defer or batch with the next touch of these files.

---

## 1. Dead CSV fallback + never-present NDJSON key in the skill helper

**File:** `.claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py`

Two bits of defensive code reference a data shape that never actually occurs, which misleads a reader into thinking a second format exists:

- **`_csv_token_totals` (~line 224):** `int(float(row.get("nb_tokens_input_joined") or row.get("nb_tokens_input") or 0))`. The cost-report CSV is written by `CostRegistry.save_to_csv(to_records(...))`, whose records only ever carry the column `nb_tokens_input_joined` — never `nb_tokens_input`. The `or row.get("nb_tokens_input")` branch is unreachable.
- **`_sum_tokens` / `_INPUT_KEYS = ("input", "input_joined")`:** sums an `input_joined` key that is never present in a *raw* `UsageReportEvent`. `INPUT_JOINED` is synthesized later, inside `CostRegistry.complete_cost_report` (it pops `INPUT` and renames it on a copy used only for costing). The emitted event's `nb_tokens_by_category` always has `input`, never `input_joined`, so the extra key always contributes 0.

**Why it's harmless today:** neither produces a wrong total — the CSV column genuinely matches the NDJSON `input` sum, and the missing keys add 0.

**The real (latent) risk:** if the CSV schema ever *did* emit both `nb_tokens_input` and `nb_tokens_input_joined`, the union-sum logic would silently double-count input. Worth simplifying to just the column that exists.

**Fix:** drop the `nb_tokens_input` fallback; set `_INPUT_KEYS = ("input",)`. Re-confirm the CSV column name in `pipelex/cogt/usage/cost_registry.py` (`save_to_csv` + `to_records`, and the `*TokenCostReportField` enums where `NB_TOKENS_INPUT_JOINED = "nb_tokens_input_joined"`) before editing, in case it has since changed.

---

## 2. Vacuous + duplicated sentinel guard in the real-inference test

**File:** `tests/integration/pipelex/temporal/tracing/test_split_worker_real_inference_cost.py`

The test declares a local `_FAKE_RUNNER_MODEL_NAME = "split_runner_fake"` and asserts (near the end of `test_real_provider_usage_aggregates_to_nonzero_cost`):

```python
assert _FAKE_RUNNER_MODEL_NAME not in model_names, "Real inference must report a real model handle, not the fake sentinel"
```

**Problem:** this test explicitly installs `runner_act_llm_gen_text=_real_runner_act_llm_gen_text` (real inference), so the *default* fake substitute — the only thing that ever emits `"split_runner_fake"` — is never wired in. The asserted string can never appear regardless of whether real inference actually ran, so the guard can never fail (false confidence).

**Drift risk:** `"split_runner_fake"` is re-declared as a local literal instead of imported from the helper that owns it (`tests/integration/pipelex/temporal/tracing/helpers.py`, `_RUNNER_FAKE_INFERENCE_MODEL_NAME`). If the helper's sentinel is renamed, this assertion silently checks a stale string and keeps "passing" while guarding nothing.

**Fix options (pick one):**

- Drop the assertion — the adjacent `assert all(model_names)` (every usage record names a real handle) plus the non-zero-token assertions already prove real inference ran. This is the cleaner option; the sentinel-absence check adds nothing once the default substitute isn't in play.
- Or, if a guard against accidentally falling back to the fake substitute is still wanted, import `_RUNNER_FAKE_INFERENCE_MODEL_NAME` from `helpers.py` rather than re-declaring it, so a rename can't rot it.

---

## Verification

These files' tests are green as-is. After either change, re-run:

```bash
# helper (#1) — no test, just exercise it against a fresh run dir, or eyeball
# real-inference test (#2) is marked inference/llm (opt-in spend); the no-spend lane:
.venv/bin/pytest -p no:cacheprovider -q \
  tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py \
  tests/integration/pipelex/temporal/tracing/test_split_worker_cross_child_usage.py
```
