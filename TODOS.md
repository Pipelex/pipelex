# Implementation Plan — `feature/API-readiness-4`

Pipelex-side cleanup branch picking up the upstream tail of the API error-handling endeavour. The API consumer (`pipelex-api`, branch `feature/Adapt-to-pipelex-update-3`) has shipped through Phases 0-5 plus Phase A0 / A1 and is at a "finalize" moment; what remains for the API to fully discharge that endeavour is a handful of upstream-pipelex items. **This branch is those items.**

---

## Cold-start reading order

Read in this order to understand why this branch exists at all:

1. `wip/error-handling/README.md` — current state of error handling across pipelex; the high-level map.
2. `wip/error-handling/archive-todos-api-readiness-2.md` — the prior ledger (formerly the repo-root `TODOS.md`, archived 2026-05-28). This branch is the successor.
3. `../pipelex-api/wip/pipelex-changes.md` Stage 7 (items #10-#15) — the **authoritative per-item context** for five of the items on this branch. Each item there has a *What / Why / Where / How* writeup with empirical reproductions against the pinned pipelex. Do not re-derive that context here; consume it from there.
4. `../pipelex-api/TODOS.md` "Deferred / next-track work" → "Upstream-pipelex follow-ups" — names the same items at the API end, in the consumer's voice. Useful sanity check.
5. `wip/console-targets-and-agent-cli-stdout.md` and `wip/structured-logging/kickoff.md` — relevant background for the **webhook-delivery logging** item below; see the sequencing note in that section before starting.

The `test_failed_webhook_log_includes_request_id_when_set` regression test already landed on the base (`feature/API-readiness-2`, commit `74b68bd7`) and is present in the working tree — do **not** re-add it. `git log feature/API-readiness-2..HEAD --oneline` shows this branch adds only planning docs on top of that base. Everything below is what to implement.

---

## What this branch is NOT

- Not the structured-logging refactor. That has its own kick-off doc and its own future branch (`refactor/structured-logging` or similar — see `wip/structured-logging/kickoff.md`).
- Not webhook signing. That's the cross-repo lockstep track owned by `wip/security/webhook-signing.md`.
- Not a `dev` merge train. If `dev` has moved, treat that as a separate prep step, not part of this plan.

---

## Items

Six concrete items, all flagged in `pipelex-changes.md` Stage 7 or surfaced by the API-side `TODOS.md`. None blocks any API release on its own; together they discharge the upstream tail of the error-handling endeavour and let the API drop a small number of follow-up catches and workarounds.

Sequencing inside this branch is flexible — every item is independent except where called out. Suggested order is "smallest first to build momentum, then the two bigger ones."

### 1. `ErrorDomain.is_input` (and siblings) — `@property` helpers on the enum

- [x] **Status:** Done (2026-05-28). Two pieces landed in `pipelex/base_exceptions.py`: (a) `ErrorDomain.is_input` as an exhaustive-`match` `@property` (the enum-level single source of truth), and (b) a module-level `error_domain_is_input(error_domain: ErrorDomain | str | None) -> bool` that coerces the serialized form and delegates to the property — paralleling the existing `error_domain_to_http_status(...)`. The function is the one the API actually consumes: both API call sites hold `error_domain` as `str | None` (`ErrorReport.error_domain` is typed `str | None`; the problem-document dict value is a plain str), so the bare `report.error_domain.is_input` the spec sketched would not type-check. Covered by `tests/unit/pipelex/exceptions/test_error_domain.py::TestErrorDomain` (`test_is_input` + `test_error_domain_is_input`). Only `is_input` landed — `is_config` / `is_runtime` deferred until a need surfaces. The API consumes this via the editable local dependency on this worktree (no PyPI pin bump needed); the API-side switch off `== ErrorDomain.INPUT` at `api/exception_handlers.py:204,253` is being made now.
**Authoritative spec:** `../pipelex-api/wip/pipelex-changes.md` item #14.
**Where:** `pipelex/base_exceptions.py` — the `ErrorDomain` `StrEnum`.

Add `@property` helpers (`is_input`, and `is_config` / `is_runtime` as needs surface) so callers read state via `report.error_domain.is_input` instead of `report.error_domain == ErrorDomain.INPUT`. This is the canonical project remediation for single-state enum checks (see `python-standards.md`) — call sites stay one-liners, the enumeration lives in one place.

**Sequence first:** every other item benefits from being able to use the helper at call sites it touches. Trivial change; ~20 lines + a test. The API-side `archive-todos-api-readiness-2.md` Phase 3 review Q9 left two call sites in `api/exception_handlers.py` deliberately on `== ErrorDomain.INPUT` waiting for this; one follow-up commit there will switch them once this lands.

---

### 2. `EnvVarNotFoundError` should carry `error_domain = ErrorDomain.CONFIG`

- [x] **Status:** Done (2026-05-28). Added `error_domain = ErrorDomain.CONFIG` as a class attribute on `EnvVarNotFoundError` in `pipelex/system/exceptions.py`, so its rendered `ErrorReport` / RFC 7807 problem document classifies as a config-domain failure (an operator sets the missing env var, not the caller). HTTP status is unchanged — both `None` and `CONFIG` map to 500. Covered by `tests/unit/pipelex/exceptions/test_class_level_metadata.py::TestClassLevelMetadata::test_error_domain` (new `env_var_not_found` parametrize case). The API consumes this via the editable local dependency on this worktree.
**Authoritative spec:** `../pipelex-api/wip/pipelex-changes.md` item #10.
**Where:** `pipelex/system/exceptions.py` (note: moved here from `pipelex/system/environment.py` during the Phase 6 import-path moves the API already adapted to — the spec doc still names the old path).

Today `EnvVarNotFoundError` is domain-less (it's a `ToolError`; neither parent sets `error_domain`). A missing required env var is the textbook `CONFIG`-domain failure — an operator, not the caller, fixes it. Add `error_domain = ErrorDomain.CONFIG` as a ClassVar so the rendered `ErrorReport` / RFC 7807 problem document classifies correctly. HTTP status is unaffected (both `None` and `CONFIG` map to 500).

This is the upstream half of the "original bug" the entire endeavour started from — a deployment that forgot to set `COMPLETION_CALLBACK_SECRET`. The API already classifies its own config faults as `CONFIG`; this brings pipelex-authored ones into alignment.

---

### 3. `parse_concept_spec` should validate `structure` shape before iterating

- [x] **Status:** Done (2026-05-28). Two parsing functions now shape-validate raw caller input before iterating, raising typed `INPUT`-domain errors instead of leaking bare `AttributeError`/`TypeError`/`ValueError`. (a) `parse_concept_spec` (`concept_ops.py`) rejects a non-mapping `structure` and any field value that is neither a description string nor a field-spec mapping, raising `ConceptSpecError`. (b) `parse_pipe_spec` (`pipe_ops.py`) rejects a non-list `steps`/`branches` or a non-mapping entry within them, raising the new `PipeSpecError`; the raw-iterate logic moved into a shared `_normalize_sub_pipe_list(...)` helper. Both error classes now carry `error_domain = ErrorDomain.INPUT` + `_authors_caller_facing_message = True` — `ConceptSpecError` (`builder/concept/exceptions.py`) gained the domain (it was previously domain-less); `PipeSpecError` is new (`builder/pipe/exceptions.py`). Docstrings on both functions now list every exception actually raised. Covered by new cases in `tests/unit/pipelex/builder/operations/test_parse_concept_spec.py` and `test_parse_pipe_spec.py` (typed-error + INPUT-domain assertions). Verified end-to-end through both consumers: `pipelex-agent concept`/`pipe` now emit `{"error_type": "ConceptSpecError"|"PipeSpecError", "error_domain": "input"}` instead of a bug-looking bare type. Error doc pages regenerated (`pipelex-dev generate-error-pages`) — added `pipe-spec-error.md`, refreshed `concept-spec-error.md`; the run also picked up two pre-existing stale pages unrelated to this item (`env-var-not-found-error.md` from item #2, and a missing `async-execution-not-enabled-error.md`). The API consumes this via the editable local dependency on this worktree; the API-side narrow `/build/concept` + `/build/pipe` route catches are API-side follow-ups, not this branch.
**Authoritative spec:** `../pipelex-api/wip/pipelex-changes.md` item #11.
**Where:** `pipelex/builder/operations/concept_ops.py` — the `parse_concept_spec(...)` function.

The function iterates `spec_data["structure"]` before calling `ConceptSpec.model_validate(...)`. Non-dict `structure`, or fields that are neither string nor dict, leak bare `AttributeError` / `TypeError` (undocumented; the docstring only declares `ValidationError`). Empirical reproductions live in the spec doc.

Fix is upstream shape validation — either raise a typed `PipelexInputError`-equivalent, or a `pydantic.ValidationError` via a thin `model_validate(...)` over the raw input shape before the iteration. Update the docstring to list every exception actually raised.

The API today cannot safely catch these at the route — `AttributeError` / `TypeError` are also the types a real programming bug would raise, so a route-level catch would mask genuine bugs. Once this lands, the API's `/build/concept` route gets a narrow, typed catch.

While here: sweep `pipelex/builder/operations/*.py` for the same pattern (raw-iterate-then-validate). `parse_pipe_spec` has it too — it iterates `spec_data["steps"]` / `spec_data["branches"]` and calls `dict(step)` on each entry before `model_validate`, so a non-list `steps` / `branches` or non-mapping entries leak bare `TypeError` / `ValueError` ahead of validation. Route those through the same narrow shape-validation path before iterating. (The bad-`pipe_type` `ValueError` is a separate, already-documented case — that one is narrow enough to leave.)

---

### 4. `LocalStorageProvider` should wrap raw `OSError` as a `StorageLocalError`

- [ ] **Status:** Not started.
**Authoritative spec:** `../pipelex-api/wip/pipelex-changes.md` item #12.
**Where:** `pipelex/tools/storage/local_storage_provider.py` — `_store` and `_load_with_metadata`.

Today, `ENOSPC` / `EACCES` / `EROFS` / `EIO` / `FileExistsError` / TOCTOU window after `file_path.exists()` all escape as raw `OSError`. Add a narrow `try/except OSError as exc: raise StorageLocalError(msg) from exc` around the filesystem calls — mirroring the wrapping already done by `S3StorageProvider` / `GcpStorageProvider`. Empirical reproductions are in the spec doc.

**Decision:** Add a new `StorageLocalError(StorageError)` to `pipelex/tools/storage/exceptions.py`, paralleling `StorageS3Error` / `StorageGcpError` (with a `_declared_title = "Local storage error"`). Keeps per-backend differentiation consistent across the storage abstraction.

Pair-test with item #5 (S3) — both deliver on the same storage-abstraction contract; same review can cover both.

---

### 5. `S3StorageProvider` should catch the full `BotoCoreError` hierarchy

- [ ] **Status:** Not started.
**Authoritative spec:** `../pipelex-api/wip/pipelex-changes.md` item #13.
**Where:** `pipelex/tools/storage/s3_storage_provider.py` — `_load_with_metadata`, `_store`, and `public_url`.

The provider catches only three `BotoCoreError` subclasses (`NoCredentialsError`, `EndpointConnectionError`) plus `ClientError` (which is a *sibling*, not a subclass, of `BotoCoreError`). Every other `BotoCoreError` subclass — `ReadTimeoutError`, `ConnectTimeoutError`, `ConnectionClosedError`, `PartialCredentialsError`, `CredentialRetrievalError`, `ProxyConnectionError`, … — escapes unwrapped. `ReadTimeoutError` is the most likely real-world leak (transient AWS networking).

Fix: broaden each `except` block from `(NoCredentialsError, EndpointConnectionError)` to `BotoCoreError`, keeping the `ClientError` branch as a separate sibling `except`. The two service-specific branches at the top (`NoSuchKey`, `NoSuchBucket`) stay. `public_url`'s `try/except ClientError → return public URL` fallback should likely widen the same way.

**Decision:** Keep wrapping as the existing `StorageS3Error(StorageError)` — no new sub-error class needed for the broadened catch. (Symmetric to item #4's `StorageLocalError` addition.)

Lower-priority side issue noted in the spec doc: `_get_session()` runs outside every method's try block. Mention in the PR but don't gate on it.

---

### 6. Webhook-delivery SSRF DNS recheck

- [ ] **Status:** Not started. Flagged in `../pipelex-api/TODOS.md` "Deferred / next-track work" → "Upstream-pipelex follow-ups".
**Where:** `pipelex/pipe_run/delivery_executor.py` — wherever the webhook HTTP client (`httpx`) actually fires.

The API's `api/schemas/models.py::_is_disallowed_host` only blocks literal private / loopback / metadata IPs **at request time**. A callback URL like `https://attacker.example/cb` passes API-side validation while its DNS record can resolve to `169.254.169.254` / `127.0.0.0/8` / `10.0.0.0/8` when the worker later fires the webhook. The fix belongs at delivery time:

- A custom `httpx` transport / `httpcore` network backend whose connect step resolves the host, checks every resolved IP against the same private-host rule, and refuses to open the socket to a private / metadata destination. Note: on the pinned `httpx` 0.28.1, `AsyncHTTPTransport` exposes **no** resolver hook, and event hooks are `request` / `response` only — neither fires after DNS but before payload send — so a plain event hook cannot close the DNS-rebinding gap.
- Or an explicit resolve-and-connect flow: resolve the hostname (`socket.getaddrinfo`), validate each candidate IP against the rule, then connect to a vetted IP while preserving the original `Host` header / SNI — so a rebind between validation and send is impossible.
- Plus optionally an egress allowlist / proxy at the deploy layer (out of scope here — flag in the PR description so the deploy team sees it).

The literal-host check on the API side stays as a cheap first line of defense.

**Test fixture:** synthesize a webhook URL whose DNS resolves to a private IP (use a `socket.getaddrinfo`-style monkeypatch or a test resolver). Confirm the delivery aborts with a typed error (likely a new `WebhookDeliverySsrfBlocked` or similar) rather than completing the request.

**Decision — rule placement.** Create a new `pipelex/tools/network/` package (greenfield — no `network` module exists today under `pipelex/tools/`) and put the rule in `pipelex.tools.network.is_disallowed_host(...)`. The API-side `_is_disallowed_host` in `pipelex-api/api/schemas/models.py` gets re-pointed at this helper, so the CIDR set lives in one place. Follow the error-location convention: `pipelex/tools/network/exceptions.py` for `WebhookDeliverySsrfBlocked` (or whatever the typed error ends up named) — do not co-locate the error with the helper.

---

### 7. Structured `event=webhook_delivery` / `event=webhook_failure` logging — **DEFERRED to structured-logging refactor**

- [x] **Status:** Closed-by-deferral on this branch (2026-05-28). Re-scoped onto the `refactor/structured-logging` branch.
**Where (for the deferral):** `wip/structured-logging/kickoff.md` "What good looks like" — event-name emission now in scope.

The lines this item would have touched (`pipelex/pipe_run/delivery_executor.py` around 239 / 243 / 280 / 282 / 285) are exactly the lines the structured-logging refactor lists as deletion targets (`request_id_suffix` pattern, kwarg threading from commits `ceb018b5` / `07f9cce9`). Doing a narrow event-name pass on this branch would touch those lines twice.

**Follow-up actions when the structured-logging branch starts:**

- Emit `event=webhook_delivery` / `event=webhook_failure` (and `event=storage_delivery` / `event=storage_failure` for symmetry) as structured fields once the new `log.info(msg, **fields)` surface lands. Document this in the kickoff doc's destination shape.
- Re-target the API-side TODO in `../pipelex-api/TODOS.md` "Deferred / next-track work" → "Upstream-pipelex follow-ups" from this branch onto the structured-logging branch.

The API-side T6 test (`pipelex-api/tests/unit/test_webhook_recovery.py`) pins error-rendering consistency, not event names, so the API is not blocked on event-name emission.

---

## Out of scope (for this branch — recorded so they don't drift back in)

- **Structured-logging refactor.** Its own branch and PR. See `wip/structured-logging/kickoff.md`.
- **Webhook signing.** Cross-repo, lockstep. See `wip/security/webhook-signing.md`.
- **Item #15 — kajson crafted-marker exceptions.** Target repo is `kajson`, **not** `pipelex`. Belongs on a separate kajson PR. Spec lives at `../pipelex-api/wip/pipelex-changes.md` item #15; the API has a workaround in place (`_decode_body`'s widened catch tuple). Re-target there if Louis wants this on the same release train.
- **Console targets / agent CLI stdout discipline.** Independent track — `wip/console-targets-and-agent-cli-stdout.md`. Already landed in part on `fix/Log-target`.
- **Kajson untrusted-deserialization design pass.** Separate track at `../pipelex-api/wip/security/kajson-untrusted-deserialization.md` (workspace-level concern, needs `pipelex-app` + `pipelex-api-deploy` in the room).
- **API-side `pipe_code` / `pipeline_run_id` log enrichment.** Done in `pipelex-api`, not here.
- **API-side `RecursionError` in `_decode_body`.** Done in `pipelex-api`, not here.
- **API-side JSON log sink.** Done in `pipelex-api`, not here.

---

## Verification (when items land)

- `make c` + `make t` clean on every commit.
- For items #1-#5: add unit tests that pin the new behavior; the API-side test suite (`pipelex-api` with this branch pinned via the `[tool.uv.sources]` git rev) should also still pass — bump the pin and run `make c && make tp` over there as part of the PR.
- For item #6 (SSRF): integration-style test using a mock resolver. No live network.
- For item #7: depends on the sequencing decision.

---

## Pin coordination with `pipelex-api`

`pipelex-api/pyproject.toml` has a temporary `[tool.uv.sources]` git-rev pin pointing at this repo. When this branch reaches a shippable point:

1. Bump that `rev` to this branch's HEAD; run `make c && make tp` in `pipelex-api`.
2. Update the API-side `TODOS.md` "Deferred / next-track work" → "Upstream-pipelex follow-ups" — strike through the items that landed; keep the rest.
3. Update `../pipelex-api/wip/pipelex-changes.md` Stage 7 tracking table — flip the items' status.

The eventual end-state — flipping the API back to a PyPI floor (`pipelex>=<next-release>`) — is Louis-gated cross-repo release coordination; not part of this branch.

---

## Decisions taken (2026-05-28)

The open questions from the original cold-start session have been resolved. Recording here so they don't get re-litigated:

1. **Item #7 sequencing — DEFERRED to structured-logging refactor.** See item #7 above. The lines it would have touched are explicit deletion targets in `wip/structured-logging/kickoff.md`. Doing the narrow event-name pass now means touching them twice.
2. **Item #6 SSRF rule placement — SHARED HELPER.** Create `pipelex/tools/network/` (greenfield) with `is_disallowed_host(...)`. The pipelex-api side re-points its `_is_disallowed_host` at this helper. Single source of truth for the disallowed CIDR set. See item #6 above for the error-location convention note.
3. **Items #4 / #5 error class shape — NEW `StorageLocalError(StorageError)`.** Mirrors the established per-backend pattern (`StorageS3Error` / `StorageGcpError` with `_declared_title`). Item #5 keeps wrapping as the existing `StorageS3Error`.
4. **`dev` merge — NOT NEEDED.** `git log feature/API-readiness-2..origin/dev --oneline` returns 0 commits. `dev` is not ahead.
