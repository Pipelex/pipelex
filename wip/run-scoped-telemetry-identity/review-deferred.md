---
status: active
item: L-260922-75299c
---

# Deferred review findings — run-scoped telemetry identity

Findings from the `/rev` passes on this branch (profile 4) that were real but did not meet the round's bar, kept here so nothing is dropped without somewhere to chase it. Round 1 ran at bar `open`, round 2 at bar `defects`.

## One capture helper instead of the hand-rolled branches

Raised by cubic in round 1. Still **unverified** — it sorted to deferral before either round's verifier ran, so it rests on cubic's reading alone.

The identified-versus-anonymous capture shape is written out by hand at several sites: `_capture_custom_event` and `_track_to_pipelex` in `pipelex/system/telemetry/telemetry_manager.py`, both branches of `handle_trace_start` in the same file, and `_capture_event` in `pipelex/system/telemetry/posthog_span_exporter.py`. Each one reads "if the identity has a `distinct_id`, capture with it and with `groups or None`; otherwise stamp `$process_person_profile = False`".

cubic's argument for folding them into one `capture_under_identity(client, event, properties, identity)` is that the two streams cannot then drift apart again, and that the anonymous-mode defect round 1 fixed would have been a one-line change. That argument held twice: round 1's fix had to be made once in `_resolve` and then checked at every one of those sites, and round 2 found the one site nobody had checked — the exception autocapture, which was not on cubic's list because it did not resolve an identity at all.

Round 2's fix added a site rather than removing one: `DualClientExceptionCapture._capture_to_client` now writes the same branch a sixth time, though it at least collapses what used to be two copies inside that class into one. The case for the helper is therefore stronger than it was, not weaker.

It stays deferred because it is a structural refactor rather than a defect, and `RunIdentityPolicy` concentrates the part that was actually drifting — which branch a stream takes — in one place. Worth doing when that file is next opened for another reason.

## A run's exception and its spans are still two different people

Raised by `codex:adversarial` and by `code-review` in round 2, and **verified**: `exception_capture.py` captures under the stream's runless identity, while the run's `$ai_span`, `$ai_generation` and product events capture under the run-scoped one. In PostHog those are two distinct persons, so "what was this person doing before the crash" returns nothing joinable on either stream.

Round 2 fixed the half that was a privacy defect — `anonymous` mode no longer names the operator on a crash — and left this half, which is not a patch. `sys.excepthook` and `threading.excepthook` are handed `(type, value, traceback)` and nothing else, and this codebase has no ContextVar layer to read a run out of: run-scoped state rides the payload here, deliberately, because no process spans a run under Temporal. Attributing a crash to the run that caused it therefore needs a design answer — a last-known-run identity the hook may read, with its own concurrency story — rather than a change at the capture site.

Its blast radius bounds the urgency: `grep` shows the two excepthooks are the only callers of `_capture_exception`, so this fires for exceptions that escape to the top of the interpreter or of a thread. A server that handles its own exceptions never reaches it; a CLI crash does.

## The Gateway digest is a pseudonym, not a secret

Raised by `codex:adversarial` and, as a documentation finding, by cubic. The mechanism half was **verified and classified an improvement**, and the prose half was fixed in round 2.

`_make_namespaced_distinct_id` is `sha256(f"{namespace}:{run_user_id}")` truncated, with no key and no salt beyond the namespace — and the namespace, the deployment's Gateway-key hash, is itself sent in the clear as the `distinct_id` of every capture that names nobody. A party with read access to Pipelex's PostHog project can therefore fold a candidate caller id the same way and see whether the result is present, which is cheap against low-entropy ids such as e-mail addresses. That party is in practice Pipelex staff, which is what keeps this an improvement rather than a defect.

Round 2 corrected the claims instead: `docs/setup/telemetry.md` and the function's own docstring no longer say Pipelex can tell callers apart "without learning who either is".

The fix, if it is taken: fold the **raw** Gateway API key rather than its hash, since the raw key never reaches the stream. Nothing else about the construction changes, and the sentences that were weakened could then be restored. It needs the raw key carried to the resolution site, which is the reason it was not done inside a review pass.

## `user_id` has no validation and no provenance

Raised by `codex:adversarial` in round 2, **verified as a mechanism and ruled a theoretical edge case**.

`RunMetadata.user_id` is a bare `str` with no field validator — unlike `storage_scope` and `analytics_groups`, which both have one — and `pipeline_run_setup` does not validate it either. Telemetry decides a run names nobody by comparing that string against the literals in `_NON_DISTINGUISHING_RUN_USER_IDS`, keeping no record of whether the value came from the local default or from an authenticated host. A hosted caller genuinely named `local` is therefore collapsed onto the deployment fallback.

Deferred because no deployment shape was found that reaches it: the default is set in exactly one place, `PipelexMTHDSProtocol.__init__`, and a multi-tenant host must pass its own value explicitly. The cure — a nullable principal, or an identity-kind field, instead of inferring the answer from string contents — is a model change, not a review fix.

## `track_event` names `DIRECT` instead of deriving it

Raised by cubic in round 2, and correct today by its own account. `RunIdentityPolicy.make_for_operator_stream` documents itself as the single place the operator stream's policy is derived, and `track_event` is the one of those sites that writes `RunIdentityPolicy.DIRECT` literally instead of calling it. It is inside `case PostHogMode.IDENTIFIED`, so it cannot currently be wrong; a fourth mode, or a change to that mapping, would diverge there silently. An improvement, and cheap whenever that method is next edited.

## Settled in round 2, kept for the record

**The stale docstrings in the two integration-test modules** — `test_pipeline_run_setup_analytics_groups.py` and `test_pipeline_run_setup_storage_scope_gate.py` — were deferred in round 1 as unverified. Round 2 verified them: the docstrings were stale (the exporters do read the groups, and `handle_trace_start` did move below `prepare_pipe_job`), but cubic's stronger claim, that the tests would no longer fail if the gate moved back, was **refuted** — both modules also spy `get_pipeline_manager`, and `add_new_pipeline` still runs above `prepare_pipe_job`, so the pipeline half of each assertion still bites. Only the telemetry half went vacuous. Both docstrings were corrected in round 2 and say so.
