# Burn down the nondeterminism review follow-ups

> **Cold-start brief for a new session.** Mission: go through every item in [`wip/distributed-execution/nondeterminism-fix-review-follow-ups.md`](wip/distributed-execution/nondeterminism-fix-review-follow-ups.md), re-verify each against the current code, **fix the obvious ones**, **dismiss the wrong ones** (record the dismissal + reason in the follow-ups doc, don't silently delete), and **surface the judgment-call ones** in a new `.md` for discussion with the user. Do not start new feature work.

## Context (read first, in this order)

1. `wip/distributed-execution/workflow-nondeterminism-audit.md` — the verified audit. H1, H2, M1 are FIXED; the MEDIUM/LOW drift table is open but **out of scope for this session** (it has its own fix-order, steps 3–5).
2. `wip/distributed-execution/nondeterminism-fix-review-follow-ups.md` — the work list. Items came from two recall-biased multi-agent review rounds: round 1 reviewed the committed H1/M1 fixes, round 2 reviewed the H2 fix. Every item was verified once by a review agent, but **re-verify before acting** — line numbers drift and some verdicts may not survive contact with the current code.

Branch state when this brief was written: `fix/Config`, H1/M1 fixes committed; the H2 fix (new `LibraryManager.open_fresh_library` + eviction-safe `finally` reorder in `WfPipeRouter`) was uncommitted in the working tree. **Check `git status` first** — the user may have committed it since. Full suite was green (`make agent-test`) and `make agent-check` clean at that point.

## Triage protocol

For each item: re-verify → then one of:

- **FIX** — obvious, low-risk, verdict holds: implement, with tests where the repo's TDD norm applies (red first for behavior changes; no tests for trivial comment/message fixes).
- **DISMISS** — wrong, stale, or unreachable: edit the follow-ups doc to mark it dismissed with the evidence (file:line), so it doesn't get re-chased.
- **SURFACE** — real but a judgment call (design tradeoff, behavior change with ripple, multiple defensible shapes): write it up in a new `wip/distributed-execution/nondeterminism-follow-ups-decisions-needed.md` with the options and a recommendation, and leave the code alone.

## The items, with expected triage (verify anyway)

Check the box when the item reaches its terminal state (FIXED / DISMISSED / SURFACED), and append the outcome to the line — e.g. `→ FIXED (commit abc123)`, `→ DISMISSED (unreachable, see follow-ups doc)`, `→ SURFACED (decisions doc §2)`.

- [x] **0 — PRIORITY: rekey per-run worker-local state by `run_id`, not `workflow_id`** → FIXED. `wf_run_id` keys library/tracer/event-log context (and event/node-id stamps — one identity); `open_fresh_library` made pop-based (atomic, concurrent-teardown tolerant). New RED-first guard `test_wf_pipe_router_run_scoped_state_keying.py`; eviction-leak test converted to start-then-install under `wf_{run_id}`; `temporal-integration.md` keying story updated.
- [x] **0bis — cancellation test pinning the `finally`-ordering invariant** → FIXED, premise corrected: cancellation at an activity await surfaces as `ActivityError` (an `Exception`, swallowed by the best-effort except) — it CANNOT abort the finally. The guard instead forces eviction via worker shutdown: `test_wf_pipe_router_eviction_cleanup_ordering.py`, verified RED against a reordered finally.
- [x] **1 — stale runner-fallback warning message** → FIXED. Renamed `log_once_runner_fallback_engaged`, INFO level, message states the post-H1 contract; module docstring + the two unit tests updated.
- [x] **2 — dead `_event_log_contexts.clear()`** → FIXED. Deleted in `tracing/helpers.py` AND the same dead clear in `test_split_worker_real_inference_cost.py`; docstrings rewritten.
- [x] **3 — test-scaffolding dedup** → FIXED (two sub-points DISMISSED with evidence in the follow-ups doc: the enable-tracing fixture has only one copy; the extract-pages scan needs `(name, activity_id)` pairs). Shared: `make_synthetic_usage_llm_job`, `act_flush_noop`, `scheduled_activity_names` in `tracing/helpers.py`; `make_prepared_greeting_job` in `library_crate/helpers.py`.
- [x] **4 — `open_tracer` stale-eviction → delegate to `close_tracer`** → FIXED with the membership-gated warning.
- [x] **5 — skip the guaranteed-empty flush activity in costs-only LIVE** → FIXED. Determinism argument re-derived (gate inputs payload-pure; costs-only LIVE buffer provably empty; Temporal unshipped). `schedule_flush` computed in setup, consumed in finally; costs-only test arm now asserts flush ABSENT + clean replay.
- [x] **6 — trim redundant null conjuncts in the `finally`** → FIXED (folded into 5/9 rewrite; sentinels kept).
- [x] **8 — document `set_event_log` overwrite as load-bearing** → FIXED (contract comment naming the three idioms).
- [x] **9 — single-block `finally` simplification** → FIXED (sentinel + TYPE_CHECKING import gone; temporal suite green).
- [x] **10 — shared scoped-library helper for the two uuid-keyed `runtime_bridge` copies** → FIXED. Sync `scoped_library_for_crate` in `runtime_bridge/primitives/scoped_library.py`; `wf_pipe_router` left bespoke.
- [x] **11 — `LibraryManager.teardown`: forget the entry even if `library.teardown()` raises** → FIXED (`_pop_and_teardown_library`, RED-first unit tests).
- [x] **7 — graph events lack an H1-style guard** (design note) → SURFACED (decisions doc §1, with options + recommendation; ties into T3).

## Constraints and gotchas

- **Do not modify** `tests/integration/pipelex/temporal/test_wf_pipe_router_eviction_library_leak.py` to make anything pass — it's the H2 regression guard. Extending it (item 0's successor-direction case) is fine.
- Repo error-handling rules apply (`.claude/rules/python-standards.md`): no new bare `except Exception`, `try/finally` for required cleanup.
- The `finally` block in `wf_pipe_router.py` is the determinism boundary: any edit there must keep ALL synchronous worker-local cleanup before the single flush await, and the flush gate payload-pure. Re-read the block's comments before touching it.
- Items 5, 6, 9 (and 0 partially) all edit that same block — do them as one coherent change, not three diffs.
- `worker_scopes` live only in base `pipelex.toml` — a recurring false-positive bot finding; don't "fix" it.

## Acceptance

- [x] Every checklist item above is checked with its outcome appended (**FIXED** / **DISMISSED (reason)** / **SURFACED → decisions doc**), and the follow-ups doc reflects the same status per item.
- [x] `wip/distributed-execution/nondeterminism-follow-ups-decisions-needed.md` exists iff anything was surfaced, and the track `README.md` links it.
- [x] Targeted suites green along the way (temporal integration + unit libraries/reporting/tracing/graph + runtime_bridge).
- [x] `make agent-check` clean at the end.
- [x] Full `make agent-test` green at the end.
- [x] CHANGELOG `[Unreleased]` updated for any behavior change; `docs/under-the-hood/temporal-integration.md` updated if item 0 changes the keying story.

Update THIS file as you go (checkpoint style): check boxes and append outcomes as each item lands, so a further session can resume cold.
