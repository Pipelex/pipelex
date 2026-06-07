# temporal-e2e-validate skill — validation status & Step 9 fixes

Current-state record for the `/temporal-e2e-validate` skill (`.claude/skills/temporal-e2e-validate/`), captured 2026-06-02 on branch `feature/Validate-with-signatures-4-fix-dry-run`. It exists to cold-start a follow-up session: what the skill validates, what a full run found, the Step 9 skill bugs that were patched, and the open follow-ups.

## What the skill is

`/temporal-e2e-validate` validates that Pipelex pipelines execute correctly across separate Temporal worker processes. Two modes:

- **Mode 1** — pytest against a real Temporal dev server with an in-process worker (`SKILL.md`). Fast regression path; folds in the error-handling suite (activity error boundary, workflow error-report full chain, local parity arm).
- **Mode 2** — true 3-process setup (server + separate worker process(es) + submitter). Reference files under `references/`: `mode-2-setup.md` (server + workers), `mode-2-tiers.md` (Tiers 1–16), `routing-battery.md` (Step 8, v1 `activity_queues` routing), `queue-options-battery.md` (Step 9, v2 queue options + worker-runtime profiles).

## Full-run result (2026-06-02)

Everything green. The branch's dry-run changes did not break the skill's dry path.

- **Mode 1 dry** — `library_crate/` all pass; error-handling Temporal-boundary + local-parity arms pass. The 4 tests the skill calls "Known xfails" (StuffArtefact serialization / xdist flakiness) now **xpass** — stale note, not a regression.
- **Mode 2 dry** — Tiers 1, 2, 2b (cross-process registry via `act_deliver`), 3, 4, 5, 9, 12, isolation A/B/C, codec 6/7: all pass.
- **Tiers 13–16 (live error propagation)** — bad-credential worker; LLM / extract / image-gen / batch-child failures each crossed activity→workflow→submitter carrying the real classified `ErrorReport` (401), not a generic wrapper.
- **Step 8 (v1 routing)** — Tiers 10a/10b/10c all pass.
- **Step 9 (v2 queue options)** — Scenarios A–F all pass, but only **after fixing the skill bugs below**.

## Step 9 skill bugs found & patched

All pre-existing (orphan-queue validator landed in `304c3552`, "Temporal merge 3", on `main`); none caused by the dry-run branch. All fixes are in `references/queue-options-battery.md`.

1. **Orphan `q_capped` blocks router boot.** Step 9.0's base override declared `[temporal.queue_options.q_capped]` (for Scenario D's rate cap) with no `activity_queues` route referencing it. The config validator rejects an unrouted queue_options entry ("the overlay will never apply") and the router refuses to boot — taking down all Step 9 workers. **Fix:** removed `q_capped` from the base override; Scenario D now declares it in its own override block (which also routes `act_llm_gen_text -> q_capped`).
2. **Missing general runner → `--graph` hangs.** Step 9.0 spawned only specialized runners (`runner-llm`/`runner-img-gen`/`runner-extract`), each polling its own named queue. Un-routed activities — tracing (`act_flush_trace_events`, `act_assemble_graph`) and `act_deliver` — fall through to `temporal_task_queue`, which nothing polled, so any `--graph` run (Scenarios A–B) hangs on the first trace flush (`PENDING_SCHEDULED` forever). Step 8 only worked because it keeps the base `runner` from `mode-2-setup.md`. **Fix:** Step 9.0 now also spawns a general `runner` on the default queue.
3. **Scenario C unit-test node ID.** Referenced `test_resolve_dispatch.py::test_handle_options_override_queue` without the class. **Fix:** corrected to `...::TestResolveDispatch::test_handle_options_override_queue` and added a runnable command.
4. **Scenario E jinja2 path inapplicable.** Scenario E routed `act_jinja2_gen_text` to an orphan queue, but `PipeJinja2` was renamed to `PipeCompose`, which renders templates **inline** via `render_template` → `render_jinja2_async`. No pipe dispatches `act_jinja2_gen_text` anymore; it can't be triggered from a bundle. **Fix:** Scenario E now routes `act_llm_gen_text -> q_orphan` and runs the stock `native_text_sequence` bundle (objective — bounded `schedule_to_start` timeout vs hang — is activity-agnostic).
5. **Scenario E timing expectation wrong.** The old expectation ("~35s, FAIL if > 60s") ignored that each pipe step runs as a child workflow that **retries (~3 attempts)** on failure, so total ≈ `maxAttempts × schedule_to_start`. The bound itself works (verified: scheduled event carries `scheduleToStartTimeout`, fails `TIMEOUT_TYPE_SCHEDULE_TO_START`). **Fix:** Scenario E now uses a small bound (10s) and the PASS criteria account for the retry multiplier.
6. **Scenario F sanity-check targeted an unknown queue and over-claimed boot.** The "a known queue passes" check ran `--task-queue q_llm --is-unit-testing`, but `q_llm` is **not** known at that point — Scenario E's `cat >` override (full replace) declares only `q_orphan`, so the known set is `{q_orphan, temporal_task_queue}` and `q_llm` is (correctly) rejected, deterministically failing the very assertion it was meant to prove. Separately, the check claimed the worker "should start up without raising," but the task-queue validator runs early (`worker_cli.py:75`, before `Worker(...)` construction) and `--is-unit-testing` then trips a sandbox-validation error during Worker construction — so a known queue does *not* boot cleanly under that flag. **Fix:** target `temporal_task_queue` (the always-known `default_task_queue`) and assert PASS = absence of `WorkerTaskQueueUnknownError` (proceeds past the validator), with a note that the subsequent `wf_test_structured_output_cross_process` sandbox error is expected and orthogonal.

Also fixed in the same file: Scenario D's measurement (it read a single workflow, but the `act_llm_gen_text` activities live in **child** workflows, and `jq`'s `fromdateiso8601` can't parse fractional-second timestamps) — replaced with a cross-child aggregation + Python timing math; and the "all scenarios A-D are live-only" intro (C is pytest, F is CLI).

## Open follow-ups (NOT done — left for a decision)

- **Vestigial `act_jinja2_gen_text`.** Only reachable via the test fixture `pipelex/temporal/test_extras/wf_test_content_generator_child.py` (and the dry stub); still registered in `pipelex/temporal/tasks.py` and the `runner-jinja2` scope (`pipelex/pipelex.toml:665`). No pipe dispatches it (PipeCompose renders inline). Candidate for removal: the activity + its `act_jinja2_generate.py` + the `runner-jinja2` scope + the fixture path. User chose to defer; not removed.
- **Stale "Known xfails" note in `SKILL.md`** (Mode 1). The StuffArtefact-serialization xfails now xpass — the note should be refreshed or the xfail markers dropped. Out of scope for the Step 9 fixes; not patched.
- **Worker can't boot under `--is-unit-testing` (product bug, not a skill issue).** Surfaced by the Scenario F sanity-check: a sandboxed worker started with `--is-unit-testing` fails temporalio's workflow-sandbox validation on the registered test workflows, so it never boots. Queue-name-independent and orthogonal to the queue-options surface — the task-queue validator (`worker_cli.py:75`) already passed before it fires. Tracked with full evidence and likely fix locus in [unit-testing-worker-sandbox-validation.md](unit-testing-worker-sandbox-validation.md). Not investigated or fixed here.

## Cold-start: re-verify the patched skill

Prereqs: `tmux`, `temporal` CLI, `temporalio` in `.venv`. Start the dev server if down: `tmux new-session -d -s temporal-server 'temporal server start-dev'`. Note: `[temporal.search_attributes].enabled = false` on this branch, so `pipelex setup-temporal-namespace` registers nothing and the worker boot audit is skipped.

To re-verify Step 9 end-to-end, follow `references/mode-2-setup.md` then `references/queue-options-battery.md` Step 9.0 → Scenarios A–F → Step 9.t. Step 9 is **live** for A/B/D/E (real LLM + image-gen + extract calls — costs money); C is pytest, F is CLI-only. Watch for the two failure modes the fixes address: router refusing to boot (orphan queue) and `--graph` runs hanging (missing general runner). Every command must run under a hard `timeout` per the skill's Timeouts policy.

The skill itself is not in `pytest` — verification is running it. A clean teardown leaves only `temporal-server` running, `.env` untampered (Tiers 13–16 tamper it transiently), and no `.pipelex/pipelex_temporary_override.toml`.
