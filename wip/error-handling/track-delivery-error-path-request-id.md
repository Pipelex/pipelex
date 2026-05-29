# track: request_id correlation on delivery error paths

**Status:** open. Surfaced by `/code-review xhigh` on commit `07f9cce9`. Decision: TBD.

**TL;DR:** Commits `ceb018b5` (Temporal) and `07f9cce9` (direct-mode) thread `request_id` through `DeliveryExecutor` and into the **success-path** completion log lines. The **failure-path** log/error messages in the same executor still don't carry the field — same correlation gap the feature was meant to close, just on the unhappy path. Three lines in `delivery_executor.py`, plus one debug log in `pipe_run.py`.

## Context

Greptile's "Delivery logs lose request" PR comment was scoped to "the storage/webhook completion logs don't carry the inbound `X-Request-ID`." We addressed it twice:

- `ceb018b5` — `DeliveryActivityArg.request_id` plumbed through to `DeliveryExecutor.execute` and into the **two success log lines** in `_store_results` and `_notify_webhook`.
- `07f9cce9` — direct-mode `PipeRun.run` forwards `pipe_job.job_metadata.request_id` to `DeliveryExecutor.execute` so non-Temporal dispatchers don't lose correlation.

Both commits stopped at the success-path log lines. The failure-path messages — which is exactly where operators most want the correlation — still emit `pipeline_run_id=...` without `request_id`.

## The open gap

Three error-message constructions in `pipelex/pipe_run/delivery_executor.py`, and one debug log in `pipelex/pipe_run/pipe_run.py`:

| Site | Current shape (no request_id) | Trigger |
|---|---|---|
| `delivery_executor.py:243` | `f"Storage delivery failed for pipeline_run_id={pipeline_run_id}"` | Any exception inside `_store_results` (S3 write, key generation, serialization) |
| `delivery_executor.py:282` | `f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: HTTP {exc.response.status_code}"` | Webhook returns 4xx/5xx |
| `delivery_executor.py:285` | `f"Webhook delivery failed for pipeline_run_id={pipeline_run_id}: {exc}"` | Network-level failure (`httpx.RequestError`) |
| `pipe_run.py:79` | `f"Executing delivery for pipeline_run_id={pipeline_run_id}, status={status}"` (debug-level entry log) | Every delivery, both modes |

All four lines have `request_id` (or could have it) in local scope — `_store_results` and `_notify_webhook` already accept the kwarg; `pipe_run.py:79` runs in a function where `pipe_job.job_metadata.request_id` is in scope.

## Case for closing it

- **Completeness of the stated feature.** The point of threading `request_id` was operator correlation across the delivery phase. Operators most need that correlation when something fails — failed webhooks are exactly when they grep logs for the inbound request id. Leaving the failure messages uncorrelated defeats half the value.
- **Consistency.** Success-path log lines carry the field; failure-path messages don't. Any operator who reads logs will notice the asymmetry and learn the wrong heuristic ("request_id is on success lines only — guess I have to correlate by pipeline_run_id when things break").
- **Cheap.** The exception-path messages already have `pipeline_run_id` interpolated; adding the same conditional suffix that the success path uses is mechanical. No new arguments to thread (the kwarg is already in scope at all three executor sites). Test changes are small.
- **The feature isn't done until this is done.** The PR review thread for greptile's #3 finding is still open — closing it with "we did half" invites a re-flag.

## Case for leaving it

- **Out of strict scope.** Greptile's comment quoted the `completion log` lines specifically. Failure-path error messages were not in their report. The discipline we just enforced on fix #2 (match the reviewer's scope, no scope creep) argues for parsimony.
- **The failure already raises a typed exception.** `WebhookDeliveryError` / `StorageDeliveryError` propagate; the receiving code in `pipe_run.py:89-96` and the Temporal activity boundary both log the failure with their own (already-bound) context. The local `msg=` on the exception is one of several ways the failure surfaces — operators have other paths to the correlation.
- **Severity.** No data loss, no incorrect behavior. Worst case: operators have one extra hop to correlate (look up the pipeline_run_id → request_id mapping elsewhere). Compared to the original bug (delivery completion logs uncorrelated at all), the marginal value is smaller.
- **Pre-existing.** These four lines were as they are before this PR. Fixing them is feature-extension, not regression-repair. Could ride a separate, narrower PR.
- **Altitude flag.** The previous code review noted that per-line manual threading doesn't scale; a request-bound contextvar or structured-log adapter would close all these lines at once without three more manual edits. If we're going to fix the failure-path lines, the question of "do it the same manual way OR do the higher-altitude fix" reopens.

## My read

**Close the three executor error-path lines in a small follow-up commit; defer the `pipe_run.py:79` debug log and the altitude refactor.**

Rationale:

- The three executor lines are the operator-visible asymmetry. Closing them removes the "request_id is only on success" footgun and makes the feature contract symmetric.
- They cost almost nothing — the `request_id_suffix = f", request_id={request_id}" if request_id is not None else ""` helper line already exists in both `_store_results` and `_notify_webhook` for the success log; reusing the same variable on the failure message is two characters of insertion per site (plus passing through to `_store_results`'s raise — already in scope there).
- The debug entry-point log in `pipe_run.py:79` is debug-level and lives in the dispatcher, not the executor. Lower value, different file. Drop from this follow-up.
- The altitude refactor (contextvar) is the right long-term answer but is a separate, larger change. Threading the field once more is acceptable when the fix is mechanical and the long-term answer is still on the open list.

## If we do it

Single commit on `feature/API-readiness-2`, scoped to `pipelex/pipe_run/delivery_executor.py`:

- `_store_results` line 243 — append the existing `request_id_suffix` variable to the error message. (Already constructed at line 238 in the same function.)
- `_notify_webhook` lines 282 and 285 — both error-message constructions. Lift `request_id_suffix` (currently defined at line 279 after the success branch) to the top of the function so both the success and both failure messages can reuse it.
- One new test in `tests/unit/pipelex/pipe_run/test_delivery_executor.py` pinning that the storage-failure and webhook-failure exception messages carry `request_id=...` when set. Mirror the existing success-path test scaffolding (`mocker.spy(pipelex_log, "info")` won't help here since the field is on the **exception** `msg`, not a log line — assert on `str(exc)` from the raised exception inside `pytest.raises(WebhookDeliveryError) as exc_info`).

Sketch commit message:

```
fix(delivery): include request_id in DeliveryExecutor failure messages

Closes the asymmetric correlation gap left by ceb018b5 / 07f9cce9:
success-path completion logs carry request_id, but the matching
exception messages on storage/webhook failure paths still did not.
Operators correlating failed deliveries to inbound X-Request-ID had
to fall back to pipeline_run_id. Three error messages in
delivery_executor.py now carry the same conditional ", request_id={...}"
suffix the success lines use.

Deferred: the pipe_run.py:79 debug entry-point log and the altitude
refactor to a request-bound contextvar.
```

## Decision criteria

Push toward **close now** if:
- The PR thread on greptile's "Delivery logs lose request" comment is still open and we don't want to leave it for a re-flag.
- Operators have already raised an issue about asymmetric correlation in delivery failures.
- Cost of the fix stays as small as sketched (single-file, single-commit, one regression test).

Push toward **defer** if:
- We're racing the merge of `feature/API-readiness-2` and any further change widens the audit surface.
- We want to land the altitude refactor (contextvar / structured-log adapter) first and not pay the per-line cost twice.
- The greptile thread is already closed and a separate PR for the failure-path is acceptable.

## References

- Commit `ceb018b5` — `feat(delivery): thread request_id through DeliveryExecutor for cross-phase log correlation` (success-path lines).
- Commit `07f9cce9` — `fix(delivery): forward request_id from PipeRun direct-mode dispatcher to DeliveryExecutor`.
- `/code-review xhigh` outputs from both review passes — error-path findings #1-#3.
- PR #943, greptile comment thread `PRRT_kwDOOwmMFc6FHCBU`.
