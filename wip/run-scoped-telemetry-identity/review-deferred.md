---
status: active
item: L-260922-75299c
---

# Deferred review findings — run-scoped telemetry identity

Findings from the `/rev` passes on this branch (profile 4) that were real but did not meet the round's bar, kept here so nothing is dropped without somewhere to chase it. Round 1 ran at bar `open`, round 2 at bar `defects`, rounds 3 to 5 at bar `necessity`; round 5 ran past the ladder's cap of four on Louis's call, focused on the exception path.

## One capture helper instead of the hand-rolled branches

Raised by cubic in round 1. Still **unverified** — it sorted to deferral before either round's verifier ran, so it rests on cubic's reading alone.

The identified-versus-anonymous capture shape is written out by hand at several sites: `_capture_custom_event` and `_track_to_pipelex` in `pipelex/system/telemetry/telemetry_manager.py`, both branches of `handle_trace_start` in the same file, and `_capture_event` in `pipelex/system/telemetry/posthog_span_exporter.py`. Each one reads "if the identity has a `distinct_id`, capture with it and with `groups or None`; otherwise stamp `$process_person_profile = False`".

cubic's argument for folding them into one `capture_under_identity(client, event, properties, identity)` is that the two streams cannot then drift apart again, and that the anonymous-mode defect round 1 fixed would have been a one-line change. That argument held twice: round 1's fix had to be made once in `_resolve` and then checked at every one of those sites, and round 2 found the one site nobody had checked — the exception autocapture, which was not on cubic's list because it did not resolve an identity at all.

Round 2's fix added a site rather than removing one: `DualClientExceptionCapture._capture_to_client` now writes the same branch a sixth time, though it at least collapses what used to be two copies inside that class into one. The case for the helper is therefore stronger than it was, not weaker.

cubic raised it again in round 3, unprompted and from a clean context, making it the only finding to appear in all three passes.

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

## pipelex-api's `single-tenant` is a placeholder the set does not know

Raised by cubic in round 4, and **not verified** — it sorted to deferral before the verifier ran. **The stopgap was taken after round 4**, once `pipelex-api/api/routes/pipelex/pipeline.py` confirmed the default: `SINGLE_TENANT_USER_ID` now lives in `pipelex/system/storage_scope.py` beside `LOCAL_USER_ID` and is in the set, so pipelex-api can import the one string rather than spell its own. The model change below remains the cure.

`_NON_DISTINGUISHING_RUN_USER_IDS` in `pipelex/system/telemetry/telemetry_identity.py` holds `local` and `dry-run-no-user`. cubic reports that pipelex-api returns `SINGLE_TENANT_USER_ID = "single-tenant"` for every run on a single-tenant deployment, which is the same kind of shared placeholder: once pipelex-api pins this version, every such deployment's runs would land on one PostHog person named `single-tenant`, and Langfuse would receive it as `langfuse.user.id`. It is one more instance of the section above — identity absence inferred from string contents — and the cure is the same: a nullable principal carried from the host, rather than a longer list of reserved strings. Adding the string to the set is the cheap stopgap if pipelex-api pins this version before that model change lands.

## `track_event` names `DIRECT` instead of deriving it

Raised by cubic in round 2, and correct today by its own account. `RunIdentityPolicy.make_for_operator_stream` documents itself as the single place the operator stream's policy is derived, and `track_event` is the one of those sites that writes `RunIdentityPolicy.DIRECT` literally instead of calling it. It is inside `case PostHogMode.IDENTIFIED`, so it cannot currently be wrong; a fourth mode, or a change to that mapping, would diverge there silently. An improvement, and cheap whenever that method is next edited.

## Anonymous mode is a claim about PostHog, and the prose does not always say so

Raised by `code-review` in round 3. Real but narrower than reported, and **not verified** — it sorted to deferral before the verifier ran.

`make_run_identity_span_attributes` writes `pipelex.run.user_id` and `pipelex.run.analytics_groups` onto every span unconditionally, and sets `langfuse.user.id` on `is_langfuse_enabled` alone. The operator's `custom_posthog.mode` is read only by the PostHog exporters, through `RunIdentityPolicy.NONE`. So an operator running `mode = "anonymous"` with Langfuse or an OTLP exporter enabled does see per-caller ids at those destinations.

Whether that is a defect turns on what the mode is a claim about. `custom_posthog.mode` governs the operator's PostHog stream, and the docs site scopes it correctly — "the runtime identifies nobody **on your stream**". Langfuse is a separate opt-in with its own configuration, and prompts and completions already reach it unredacted, so an operator who enabled it has already consented to far more than a user id. `code-review`'s own reading is that the prose overreaches rather than the code misbehaving.

What is genuinely loose is the CHANGELOG sentence, which sits in a paragraph that also states the span behaviour plainly and so can be read either way. The cure is either to scope the claim to PostHog in that entry, or to gate the Langfuse attribute on the same decision the PostHog exporter takes — a design question about whether one operator setting should reach a second vendor's destination, which is why it was not settled inside a review pass.

## `TelemetryIdentity.is_anonymous` is a second way of asking one question

Raised by `code-review` in round 3 as a cosmetic sibling of its freeze finding, and **not verified**.

All the capture sites branch on `identity.distinct_id` being truthy; `is_anonymous` is referenced only from tests. Two ways of asking the same question, with nothing keeping them in step — either make it the one the capture sites use, or drop it. Cheap either way, and a judgement about which reads better at the call sites rather than a defect.

## Crash redaction goes by class, so a wrapper's message still carries the text

Raised by cubic and `codex:adversarial` in round 5, and **verified**; filed as `L-260923-65619d`, which carries the reproductions. An error of another class that copied a `PipelexError`'s text into its own message — `raise RuntimeError(f"failed: {error}") from error`, or `pipe_spec.py`'s `ValueError(str(exc)) from exc` — sends that text on both streams, and `PromptContentError`, `PipeValidationError` and `ConceptValueError` are not `PipelexError` subclasses, so their messages are never redacted. It predates the branch, which narrowed it: on `origin/dev` the linked `PipelexError` went out verbatim too. Round 5 corrected the prose that implied otherwise — the `_sanitized_exception_arg` and `_plain_copy` docstrings and the CHANGELOG headline now state the class limit.

## A CLI failure may never reach the Pipelex stream when both streams are on

Noted by round 5's verifier from reading the code, and **not verified**. `telemetry_context()` is PostHog's `new_context()`, which captures on `posthog.default_client` only — the operator's client whenever one exists — and the CLI turns every failure into `typer.Exit`, so the excepthook never runs. With both streams enabled a CLI failure would then reach the operator's project and not Pipelex's. The same holds on `origin/dev`; the CHANGELOG's "both telemetry streams record a crash" is about unhandled exceptions, which this is not.

## Settled in rounds 2 to 5, kept for the record

**The stale docstrings in the two integration-test modules** — `test_pipeline_run_setup_analytics_groups.py` and `test_pipeline_run_setup_storage_scope_gate.py` — were deferred in round 1 as unverified. Round 2 verified them: the docstrings were stale (the exporters do read the groups, and `handle_trace_start` did move below `prepare_pipe_job`), but cubic's stronger claim, that the tests would no longer fail if the gate moved back, was **refuted** — both modules also spy `get_pipeline_manager`, and `add_new_pipeline` still runs above `prepare_pipe_job`, so the pipeline half of each assertion still bites. Only the telemetry half went vacuous. Both docstrings were corrected in round 2 and say so.

**Round 3 found two defects on the exception path, both predating the branch and both fixed.** The privacy redaction replaced a `PipelexError`'s message only when the error arrived bare, never in the `(type, value, traceback)` form an excepthook produces — which is the only form the autocapture has — so a message repeating the caller's own input went out verbatim, reachable on the shipped default because `custom_posthog.mode = "off"` still builds the Gateway client that installs the hooks. And PostHog stamps an error once a client has captured it and drops any later capture of that object, so of the two streams only the first ever recorded a crash, which meant round 2's deployment group was never recorded anywhere. `git` dates both to v0.18.0; the branch changed their shape without introducing either, and made the second consequential by adding the group that never shipped. `tests/unit/pipelex/system/telemetry/test_exception_capture_sdk_contract.py` now exercises both against real PostHog clients, because round 2's `MagicMock(spec=Posthog)` could see neither.

**The `analytics_groups` module docstring** said "no exporter reads the mapping yet, so do not take the field's presence as evidence that a span or an event is already grouped by it" — false as of this branch, and the file is outside the diff, which is why rounds 1 and 2 swept past it. Corrected in round 3.

**The `RunMetadata` freeze** was raised by cubic and `code-review` as an unrecorded breaking change, and `code-review` additionally warned that a dependent repo might reassign a field, `RunMetadata` being on the import surface `pipelex-server/transport/` consumes. That half was **refuted**: `pipelex-server/transport/` and `pipelex-api` contain no `RunMetadata` field assignment, `pipelex-server`'s four sites are all on `mocker.MagicMock()` stubs in `pipelex_temporal` tests, and there are no `setattr` or `object.__setattr__` escape hatches anywhere. The documentation half was taken — the freeze now has a `Changed` entry.

**Round 4 found round 3's crash redaction incomplete, and one regression in its mark clearing; both fixed.** The redaction replaced a `PipelexError` only at the top of what it was handed, while PostHog sends every error it reaches through `__cause__`, `__context__` and the members of an exception group, and reads `sys.exc_info()` itself when handed nothing — so `raise RuntimeError(...) from pipelex_error`, an error raised while handling one, or a `TaskGroup` failure still sent the message verbatim to both streams. The verifier reproduced each against the real SDK. `_sanitized_exception_arg` now redacts a copy of the whole graph and resolves the argument-less form first. Separately, round 3 cleared PostHog's capture marks before the first stream as well as the second, which erased the mark a host's own `posthog.capture_exception()` had left, so an error the host captured and re-raised was recorded twice. The hook now skips an error already marked when it runs and clears marks only between the streams, and the privacy wrapper carries the mark from the redacted copy it sent back onto the caller's error — which also closes the older duplicate where a host's capture of a `PipelexError` marked only the stand-in. The Codex adversarial reviewer re-raised the pseudonym, the reserved-string and the crash-attribution findings above, which stay deferred as recorded.

**Round 5 found two defects in round 4's own changes on the exception path; both fixed.** The privacy wrapper resolved `capture_exception()`'s argument-less form inside the sanitizer only, so the "already captured" check and the mark carried back both saw `None`: a host doing `except PipelexError: posthog.capture_exception(); raise` had the redacted copy marked and the live error not, and the excepthook sent it again on both streams. It now resolves `sys.exc_info()` first. And the graph walk round 4 added ran unguarded before PostHog's own `try`, so a chain of about five hundred links or an argument the SDK would decline raised into the host's `except` block — and could replace the original error inside the CLI's `new_context()`. The reach check is a loop now, as PostHog's walk is, and anything the redaction cannot complete drops the capture with a debug line rather than raising or sending the original. The Codex adversarial reviewer re-raised the crash-attribution finding above, which stays deferred.
