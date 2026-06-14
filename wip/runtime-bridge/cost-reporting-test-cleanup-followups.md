# Cost-reporting test additions — cleanup follow-ups

**Status:** 🧹 Optional cleanups, no correctness impact. Items #1–#2 surfaced by a code review of the distributed-cost-reporting test additions (see [`distributed-cost-reporting-test-coverage.md`](distributed-cost-reporting-test-coverage.md), "Resolution (as-built)") and are resolved. Item #3 surfaced on the v0.32.0 release PR #977 and is deferred (dev/test helper only). The reviews found **no shipped-code bugs**; these are cosmetic dead-code / weak-assertion / test-helper-correctness items.

---

## 1. Dead CSV fallback + never-present NDJSON key in the skill helper ✅ DONE

**Resolution:** Verified against `pipelex/cogt/usage/cost_registry.py` and applied the fix. `INPUT_JOINED` is written into an `nb_tokens_by_category` dict only inside `complete_cost_report` (which `pop`s `INPUT` first), and the CSV is written exclusively from completed reports — so the column is always `nb_tokens_input_joined`, never `nb_tokens_input`. Raw NDJSON `UsageReportEvent`s only ever carry `input`. Dropped the `nb_tokens_input` CSV fallback and set `_INPUT_KEYS = ("input",)`. (Note: a `NB_TOKENS_INPUT = "nb_tokens_input"` enum value does exist in `llm_report.py`, but it is never emitted into a record, so the conclusion holds.)

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

## 3. Global CSV selection in the cross-worker cost assert ⏭️ DEFERRED

**File:** `.claude/skills/temporal-e2e-validate/scripts/assert_cross_worker_cost.py` (`_csv_token_totals`, ~lines 54-75)

**Status:** ⏭️ Deferred — dev/test helper only (not shipped library code). Surfaced by **greptile (P2)** on the v0.32.0 release PR #977; left open on that PR for a fast-follow.

`_csv_token_totals(reports_dir)` picks the cost-report CSV to compare against with `sorted(reports_dir.glob("cost_report*.csv"))[-1]` — the lexicographically-latest file in the **global** reports dir — even though the caller passes the run-specific `--run-dir` for the NDJSON side of the comparison. If another run already wrote a later-numbered `cost_report*.csv`, the assert compares the current run's NDJSON usage against a **stale CSV from a different run**, which can fail a good run or pass a bad one.

This is the same helper as item #1, but a distinct concern: item #1 was about the *column* read inside a row (`nb_tokens_input` fallback, ~line 224); this is about *which file* is selected (~lines 54-75).

**Why deferred, not fixed:** it's a `.claude/skills/` test helper, out of scope for the docs-only v0.32.0 release-branch pass. Real enough to fix on `dev`.

**Fix:** tie CSV selection to the run being asserted — either point `--reports-dir` at a per-run subdir (e.g. `run_dir / "reports"`) and glob there, or filter `cost_report*.csv` by the run id derived from `run_dir.name`. Re-confirm where the runner writes `cost_report*.csv` relative to `--run-dir` before choosing.

## Verification

These files' tests are green as-is. After either change, re-run:

```bash
# helper (#1) — no test, just exercise it against a fresh run dir, or eyeball
# real-inference test (#2) is marked inference/llm (opt-in spend); the no-spend lane:
.venv/bin/pytest -p no:cacheprovider -q \
  tests/integration/pipelex/temporal/tracing/test_split_worker_usage.py \
  tests/integration/pipelex/temporal/tracing/test_split_worker_cross_child_usage.py
```
