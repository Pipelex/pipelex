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

- [ ] **0 — PRIORITY: rekey per-run worker-local state by `run_id`, not `workflow_id`** — verify → likely FIX, possibly SURFACE. CONFIRMED against temporalio SDK source (eviction runs the `finally`; closed-run cleanup can destroy a live successor's library under a reused workflow id — reachable via workflow `retry_policy`, reset, same-`pipeline_run_id` resubmission). The fix ripples: library id naming (`wf_{run_id}`), tracer key, event-log context key, docs that say `wf_{workflow_id}`, and the eviction test's key assumptions. If the ripple makes you hesitate, SURFACE with a concrete diff sketch instead of half-fixing.
- [ ] **0bis — cancellation test pinning the `finally`-ordering invariant** — FIX (test only). Recipe is in the doc: blocked-flush stub via `substitute_activities` (pattern in `test_wf_pipe_router_tracing_config_nondeterminism.py`), `handle.cancel()` at the flush await, assert manager + report delegate clean. Land before/with item 5.
- [ ] **1 — stale runner-fallback warning message** (`activity_event_log.py`) — FIX. Message + maybe level. Trivial.
- [ ] **2 — dead `_event_log_contexts.clear()`** in `tracing/helpers.py` — FIX. Delete + fix docstring.
- [ ] **3 — test-scaffolding dedup** (synthetic LLMJob builder, `_act_flush_noop`, history scan, Greeting setup) — FIX. Mechanical; shared helpers in `tracing/helpers.py` / `library_crate` helpers.
- [ ] **4 — `open_tracer` stale-eviction → delegate to `close_tracer`** — FIX. Caveat in doc: warn on `key in self._tracers`, not on `close_tracer`'s ambiguous `None` return.
- [ ] **5 — skip the guaranteed-empty flush activity in costs-only LIVE** — verify → FIX or SURFACE. Payload-pure gate (`emit_graph_events or run-mode DRY`) is argued legal under H1's rationale, but it changes command emission — re-derive the determinism argument yourself before trusting it. Temporal is unshipped, so no wire-compat concern. Combine with 6 + 9 (same block).
- [ ] **6 — trim redundant null conjuncts in the `finally`** — FIX. Sentinels stay (load-bearing for crate-load failure paths) — only the inner conjuncts go. Fold into 9.
- [ ] **8 — document `set_event_log` overwrite as load-bearing** — FIX. A comment; trivially safe.
- [ ] **9 — single-block `finally` simplification** (kills the `buffered_events` sentinel + TYPE_CHECKING import) — FIX. Verified equivalent; fold 5/6/9 into one edit of the block, then run the temporal suite.
- [ ] **10 — shared scoped-library helper for the two uuid-keyed `runtime_bridge` copies** — verify → FIX or SURFACE. Maintenance-only (verified: those copies don't need `open_fresh_library`). If extraction gets invasive, surface instead.
- [ ] **11 — `LibraryManager.teardown`: forget the entry even if `library.teardown()` raises** — FIX. One-liner (pop first or `del` in `finally`). Unreachable today, cheap insurance.
- [ ] **7 — graph events lack an H1-style guard** (design note) — SURFACE. Already marked "no action yet" — carry it into the decisions doc with the T3 pointer rather than fixing.

## Constraints and gotchas

- **Do not modify** `tests/integration/pipelex/temporal/test_wf_pipe_router_eviction_library_leak.py` to make anything pass — it's the H2 regression guard. Extending it (item 0's successor-direction case) is fine.
- Repo error-handling rules apply (`.claude/rules/python-standards.md`): no new bare `except Exception`, `try/finally` for required cleanup.
- The `finally` block in `wf_pipe_router.py` is the determinism boundary: any edit there must keep ALL synchronous worker-local cleanup before the single flush await, and the flush gate payload-pure. Re-read the block's comments before touching it.
- Items 5, 6, 9 (and 0 partially) all edit that same block — do them as one coherent change, not three diffs.
- `worker_scopes` live only in base `pipelex.toml` — a recurring false-positive bot finding; don't "fix" it.

## Acceptance

- [ ] Every checklist item above is checked with its outcome appended (**FIXED** / **DISMISSED (reason)** / **SURFACED → decisions doc**), and the follow-ups doc reflects the same status per item.
- [ ] `wip/distributed-execution/nondeterminism-follow-ups-decisions-needed.md` exists iff anything was surfaced, and the track `README.md` links it.
- [ ] Targeted suites green along the way (`.venv/bin/pytest tests/integration/pipelex/temporal/ tests/unit/pipelex/libraries/ ...`).
- [ ] `make agent-check` clean at the end.
- [ ] Full `make agent-test` green at the end.
- [ ] CHANGELOG `[Unreleased]` updated for any behavior change; `docs/under-the-hood/temporal-integration.md` updated if item 0 changes the keying story.

Update THIS file as you go (checkpoint style): check boxes and append outcomes as each item lands, so a further session can resume cold.
