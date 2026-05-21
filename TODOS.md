# TODOS — pipelex changes for the pipelex-api error-handling refactor

This worktree (`feature/API-readiness`) carries the **pipelex-side** companion work for the `pipelex-api` error-handling design. The original per-item spec is in [`wip/error-handling/changes-for-api-early-draft.md`](wip/error-handling/changes-for-api-early-draft.md); the deviations we are taking from that spec — and *why* — are documented in [`wip/error-handling/api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md). The cross-repo consumer (the API) lives in the side-by-side worktree [`../pipelex-api/wip/error-handling/`](../../pipelex-api/wip/error-handling/).

This file is the **execution plan** — what to land, in what order, with hard-stop checkpoints. It consolidates the error-handling items from the original spec. The original spec's webhook-signing item (item 9) is split out as a separate security track — see [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md). It is security work, not error-handling work; the cross-repo coordination it needs is independent of this plan's PR series. See [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) for the full rationale on the error-handling consolidation.

---

## Decisions locked in

The plan reflects these decisions; no further re-litigation in the items below.

- **`ErrorReport` becomes a `BaseModel`** (`model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`). We drop the `@pydantic.dataclasses.dataclass` form. The existing Temporal data converter already handles `BaseModel` round-trips — no kajson surgery needed. (Was Item D-2's open question.)
- **`ErrorReport.title` and `type_uri` are required `str`**, not `str | None`. Every fresh report carries them. A payload missing them fails `from_dict`, which `recover_error_report` synthesizes as `UnrecoverableWorkflowFailureError` (Item D-1) — the correct behavior under "no backward-compat shims."
- **`title` and `type_uri` are wrapper-wins under cause-chain enrichment.** When `PipeRouterError` wraps `CogtError`, the resulting report carries `error_type="PipeRouterError"`, `title=PipeRouterError.title()`, `type_uri=PipeRouterError.type_uri()` — the identity triplet (`error_type` / `title` / `type_uri`) stays consistent. Classification fields (`error_category`, `provider`, `retryable`, `user_action`, `model`, `provider_metadata`) continue to backfill from the cause as today. The deeper-cause *identity* (its own `error_type` / `title` / `message`) is **not** preserved on the current flat `ErrorReport`; consumers who need Sentry-style cause-trail visibility get it via the deferred `causes` follow-up (see "Deferred follow-ups" below).
- **`request_id` propagates via `JobMetadata` only.** No ContextVar layer for propagation — Temporal serializes the activity arg; only fields on `JobMetadata` cross the worker boundary. Activity-side log binding reads `arg.<path>.job_metadata.request_id` directly from the arg.
- **`UnrecoverableWorkflowFailureError` lives in `pipelex/temporal/exceptions.py`**, not `base_exceptions.py`. It's a Temporal-flow-specific synthesis concept.
- **`errors_config` lives under `Pipelex` config**: `get_config().pipelex.errors_config.base_uri`. Consistent with `pipe_run_config`, `pipeline_execution_config`, etc.
- **`error_category` is kept in STRICT mode** alongside the other stable identifiers. Revisit only if a deployment surfaces it as a data-leak.
- **Stage 3 acceptance covers the full `WfPipeRun` chain**, not just `WfPipeRouter`. The existing test bypasses `WfPipeRun`; the new test exercises the outer wrap so the inner child's report survives.
- **`DisclosureMode.STRICT` is a classification-projection for server-side errors, NOT a path-leak shield.** `INPUT`-domain reports pass through unchanged in STRICT mode (caller-influenced; reflecting back is part of the contract). `CONFIG`/`RUNTIME` reports get redacted. This asymmetry is documented on the `DisclosureMode` docstring itself (Item C) — the entry point a developer reads when wondering "what does STRICT mean?" — so the contract can't be silently misread. If an INPUT message could surface a server-resolved path or secret, the fix is to repair the upstream message, not to expand STRICT mode.
- **`WorkflowExecutionError` is a wrapper-loses exception to the wrapper-wins rule.** At `pipelex/temporal/exceptions.py:35-43`, `WorkflowExecutionError.to_error_report()` returns `self.error_report` verbatim, bypassing `_enrich_error_report_from_cause()`. The recovered inner classification (`error_type` / `title` / `type_uri` / `error_category` / `provider`...) is preserved as-is because the Temporal serialization boundary would otherwise drop it — the *whole point* of recovering the report is to restore the worker-side identity, not to overwrite it with the cross-boundary wrapper's identity. This is the **only** such carve-out in the hierarchy; do NOT "fix" it by adding `_enrich_error_report_from_cause(report)` to the override during Item A implementation. The wrapper-wins rule applies to in-process wrapping (`PipeRouterError(CogtError)`); the wrapper-loses behavior applies to cross-boundary recovery (`WorkflowExecutionError(recovered_report)`).

---

## Approach

- **Stages map to API-plan dependencies, not effort.** Land in stage order so the API team can start consuming primitives as early as possible.
- **TDD red-green per item.** Add the failing test against the desired surface first, then implement until it passes. Pre-existing tests under `tests/unit/pipelex/test_base_exceptions.py`, `tests/unit/pipelex/test_error_report_from_dict.py`, `tests/unit/pipelex/pipe_run/test_delivery_executor.py`, `tests/unit/pipelex/temporal/test_recover_error_report.py`, and `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` are the natural homes for the new cases.
- **After every item:** run `make agent-check` and `make agent-test`. Both must pass before checking off the item.
- **No backward-compatibility shims, no curate-a-subset hedges, no "consumer fallback for missing data" patterns.** Pipelex owns the defaults so every consumer gets the same behavior automatically.

---

## Stage 1 — Foundations *(unblocks `pipelex-api` Phase 0)*

### [x] Item A — `PipelexError.title()` + `type_uri()` with auto-derive defaults *(merges spec items 1+2)*

- **Files:**
    - `pipelex/base_exceptions.py` — new classmethods + new `ErrorReport` fields.
    - `pipelex/tools/misc/string_utils.py` — add `pascal_case_to_kebab(name: str) -> str` next to the existing `pascal_case_to_*` helpers (it's the same module's concern; no new helper module).
    - `pipelex/system/configuration/configs.py` — new `ErrorsConfig(ConfigModel)` with `base_uri: str`, mounted under `Pipelex` as `errors_config`.
    - `pipelex/pipelex.toml` — `[pipelex.errors_config]` section with `base_uri = "https://pipelex.dev/errors"`.
- **Surface:**
    ```python
    class PipelexError(Exception):
        _declared_title: ClassVar[str | None] = None
        _declared_type_uri: ClassVar[str | None] = None

        @classmethod
        def title(cls) -> str:
            return cls._declared_title or _humanize(cls.__name__)

        @classmethod
        def type_uri(cls) -> str:
            if cls._declared_type_uri is not None:
                return cls._declared_type_uri
            base = get_config().pipelex.errors_config.base_uri
            return f"{base.rstrip('/')}/{pascal_case_to_kebab(cls.__name__)}"
    ```

    `ErrorReport` (now a `BaseModel` — see Item D-2 in Decisions locked in) gains:

    ```python
    title: str
    type_uri: str
    ```

    Both **required**. `PipelexError.to_error_report()` populates them from `type(self).title()` / `type(self).type_uri()`. They round-trip through `model_dump` / `model_validate`.

- **`_humanize` rule.** Strip a trailing `"Error"` from the class name (if present), then `pascal_case_to_sentence(...)` (existing helper — already handles acronyms like `JSON`, `URL`, `API`). Single-token classes (`CogtError`) become `"Cogt"` — these need a curated `_declared_title` (see next bullet).
- **`type_uri()` and config readiness.** No fallback constant. `pipelex.errors_config.base_uri` is a required config field with the default value (`"https://pipelex.dev/errors"`) shipped in `pipelex/pipelex.toml`. If config is not loaded when `type_uri()` is called, that is a programmer error and should raise loudly — do not paper over it with a module-level default. Boot-sequence errors that pre-date config load are already extremely rare and surface via other channels.
- **Curated overrides shipped with this item** (concrete list, not "to be discovered later"):
    - `PipelexError._declared_title = "Pipelex error"`
    - `PipelexUnexpectedError._declared_title = "Unexpected internal error"`
    - `SecurityError._declared_title = "Security policy violation"`
    - `CogtError._declared_title = "AI inference failed"`
    - `EnvVarNotFoundError._declared_title = "Environment variable not set"`
    - **Wide sweep at implementation time.** With ~267 `PipelexError` subclasses in the codebase, do a focused pass through every leaf class whose auto-derived title reads as a noun, an awkward fragment, or grammatically wrong. Curate them in this same PR. Do NOT defer to a follow-up.
- **Migration sweep — raw `ErrorReport(...)` constructions** (must land in the same PR since both fields become required):
    - **Production sites (3):**
        - `pipelex/base_exceptions.py:135` — `PipelexError.to_error_report()`: populate `title=type(self).title()`, `type_uri=type(self).type_uri()`.
        - `pipelex/base_exceptions.py:166` — `_enrich_error_report_from_cause()` rebuild path: propagate `title=report.title`, `type_uri=report.type_uri` (wrapper-wins, per "Decisions locked in").
        - `pipelex/cogt/exceptions.py:88` — `CogtError.to_error_report()` override: same as the base class.
    - **Test fixtures (~10):** mixed strategy.
        - Where the test is *about* serialization / round-trip / disclosure / RFC 7807 (`test_error_report_from_dict.py`, `test_base_exceptions.py`, the new Item C tests): construct with **real** `title="..."` / `type_uri="https://pipelex.dev/errors/..."` values. The test is honest about the contract.
        - Where the test is about classification / domain / HTTP status and doesn't exercise `title`/`type_uri` (`test_error_http_status.py`, `test_error_domain.py`, the various `test_workflow_*_error_*.py` fixtures): introduce a small helper `make_error_report(...)` in a tests-only conftest with `title="Test error"` / `type_uri="https://test.pipelex.dev/errors/test-error"` defaults, so each fixture line stays a single readable call.
        - **Special case — `tests/unit/pipelex/test_base_exceptions.py::test_error_report_constructable_without_cogt_exceptions_loaded`** (the cold-import subprocess test). This test will break twice under Item A: (a) `ErrorReport(error_type='X', message='m')` is now a `ValidationError` (missing required fields), and (b) `PipelexConfigError('boom').to_error_report()` calls `type_uri()` → `get_config()` → `RuntimeError` because the subprocess never bootstraps Pipelex. Per the "Decisions locked in" no-fallback-constant rule, this is by design — config-less `type_uri()` calls must raise loudly. The fix preserves the test's original intent (verify `ErrorReport` is fully defined without `cogt.exceptions` being loaded) by dropping the `to_error_report()` line and constructing `ErrorReport` directly with explicit `title="X"` / `type_uri="https://pipelex.dev/errors/x"`. Add a separate non-subprocess test elsewhere (e.g. in `test_base_exceptions.py` in a new `TestPipelexErrorTypeUri` class) that asserts `PipelexConfigError.to_error_report()` populates `title` / `type_uri` correctly — with config loaded by the normal pytest fixture chain.
- **Tests** (`tests/unit/pipelex/test_base_exceptions.py` unless noted):
    - Auto-derive: `class FooBarError(PipelexError): pass` → `FooBarError.title() == "Foo bar"`, `type_uri() == "https://pipelex.dev/errors/foo-bar"`.
    - Override wins: `class X(PipelexError): _declared_title = "Custom"` → `X.title() == "Custom"`.
    - Round-trip: `ErrorReport.model_validate(report.model_dump()).title == report.title` and same for `type_uri`.
    - **Uniqueness guard:** a test that walks `PipelexError.__subclasses__()` recursively (forcing imports of the relevant `*/exceptions.py` modules first) and asserts every class's `type_uri()` is unique. Catches future class-name collisions at CI time, not docs-build time.
    - `pascal_case_to_kebab` (in `tests/unit/pipelex/tools/misc/test_string_utils.py`):
        - Basic: `"FooBarBaz"` → `"foo-bar-baz"`.
        - Trailing acronym: `"APIError"` → `"api-error"`.
        - Embedded acronym: `"HTTPError"` → `"http-error"`.
        - No-acronym multi-word: `"EnvVarNotFound"` → `"env-var-not-found"`.
        - Numeric + acronym: `"OAuth2"` → `"o-auth2"` (consistent with `pascal_case_to_sentence("OAuth2") == "o auth2"` — pin this in the test).
        - Numeric mid-string: `"V2APIError"` → `"v2-api-error"`.
    - **`from_dict` missing-required-fields:** `ErrorReport.from_dict({"error_type": "X", "message": "m"})` raises `pydantic.ValidationError` (no `title`/`type_uri`). This is the path that `recover_error_report` (Item D-1) converts into `UnrecoverableWorkflowFailureError` — pin it here as the unit-level contract.
- **Acceptance:** consumers never humanize or kebab-case a class name themselves. The API consumes `report.title` / `report.type_uri` directly.

### [x] Item B — First-class `request_id` on `JobMetadata` *(spec item 3)*

**Propagation, not a ContextVar layer.** Temporal serializes the activity arg, so the only way `request_id` reaches the worker is by riding on a field that's part of the workflow input. That field is `JobMetadata.request_id`. There is no cross-boundary ContextVar.

- **Files:**
    - `pipelex/pipeline/job_metadata.py` — add `request_id: str | None = None` next to `pipeline_run_id` / `user_id` / `session_id`.
    - `pipelex/pipeline/pipeline_run_setup.py` — `pipeline_run_setup(...)` accepts a `request_id: str | None = None` kwarg and threads it into the `JobMetadata` it constructs.
    - `pipelex/temporal/log_temporal.py` — extend `WorkflowLog` / `ActivityLog` with an optional `request_id` kwarg on each method: `activity_log.info("...", request_id=arg.pipe_job.job_metadata.request_id)`. Implementation: pass through to `temporalio`'s logger via `extra={"request_id": ...}`. Activities that want request_id in their logs pass it explicitly. Verbose by one parameter; explicit over clever; no global mutable state.
- **Naming-collision note.** `ProviderErrorMetadata.request_id` already exists at `pipelex/cogt/inference/error_classification.py:80` and means "the provider's request ID" (OpenAI `x-request-id`, Anthropic equivalent). `JobMetadata.request_id` means "the API's inbound `X-Request-ID`". Both can appear in a single ErrorReport. Document this distinction in `JobMetadata.request_id`'s docstring; no field rename.
- **Tests:**
    - Unit: `JobMetadata(request_id="r-123")` round-trips through `model_dump_json` / `model_validate_json`.
    - Unit: `pipeline_run_setup(..., request_id="r-123")` produces a `PipeJob` whose `job_metadata.request_id == "r-123"`.
    - Integration (`tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py`): dispatch with a known `request_id`. Assert it appears in the recovered `WorkflowExecutionError.to_error_report()` chain via JobMetadata propagation (read the value off the recovered context). On a `caplog`-style assertion, verify an explicit `activity_log.info(..., request_id=...)` call inside a hook emits a log record with `request_id` in `extra`.
- **Acceptance:** a `request_id` passed to `pipeline_run_setup(...)` arrives on the worker as `arg.pipe_job.job_metadata.request_id` with no consumer-side workaround. The current `webhook.payload["request_id"]` piggyback in the API becomes obsolete.

**Checkpoint 1 — End of Stage 1** ⬇ See [Checkpoint 1 brief](#checkpoint-1--end-of-stage-1) below.

---

## Stage 2 — Rendering primitives + total recovery *(unblocks `pipelex-api` Phase 1)*

### [x] Item C — Parameterized `to_dict(disclosure_mode=)` + `to_problem_document(...)` *(merges spec items 4+6)*

- **File:** `pipelex/base_exceptions.py`
- **Surface:**
    ```python
    class DisclosureMode(StrEnum):
        """How much detail to include when serializing an ``ErrorReport`` for external surfaces.

        - ``VERBOSE``: all classification fields plus the original ``message``. Use for
          internal-trust boundaries (webhook payloads, internal RPCs) where the receiver
          decides what to expose further downstream.

        - ``STRICT``: stable identifiers only (``error_type``, ``error_domain``,
          ``error_category``, ``retryable``, ``title``, ``type_uri``). For
          ``CONFIG`` / ``RUNTIME`` reports, ``message`` is replaced with a generic
          placeholder and ``provider`` / ``model`` / ``provider_metadata`` /
          ``user_action`` are dropped.

          **``INPUT``-domain reports are returned unchanged in STRICT mode.** Their
          ``message`` is caller-influenced and reflecting it back is part of the
          contract. STRICT is a *classification-projection for server-side errors*,
          **not a path-leak shield**. If an ``INPUT`` message could surface a
          server-resolved path or secret, fix the upstream message — don't expand
          STRICT mode's scope.
        """
        VERBOSE = "verbose"
        STRICT = "strict"

    class ErrorReport(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
        ...
        def to_dict(self, disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE) -> dict[str, Any]: ...
        def to_problem_document(
            self,
            *,
            instance: str | None = None,
            request_id: str | None = None,
            disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE,
        ) -> dict[str, Any]: ...

        @classmethod
        def from_dict(cls, data: dict[str, Any]) -> "ErrorReport": ...
    ```
- **`from_dict` / `to_dict` semantics.** `to_dict(VERBOSE)` is the inverse of `from_dict`; the round-trip is preserved. `to_dict(STRICT)` is a **lossy** projection — `from_dict(to_dict(report, STRICT))` does not reconstruct the original. Document this on the docstring (with a brief "See `DisclosureMode` for the redaction rule" cross-reference rather than duplicating the rule). Webhook payloads use VERBOSE so receivers can rehydrate (`ErrorReport.from_dict(payload["error"])`); HTTP responses use whatever disclosure the deployment configured.
- **Strict redaction rule:**
    - `INPUT`-domain reports → returned unchanged (the caller's own input; reflecting it back is fine).
    - `CONFIG` / `RUNTIME` reports → `message` replaced with `"An internal error occurred."`; `provider`, `model`, `provider_metadata`, `user_action` dropped.
    - **Kept in all modes** (stable identifiers, RFC 7807-compatible): `error_type`, `error_domain`, `error_category`, `retryable`, `title`, `type_uri`.
- **`to_problem_document`** builds the RFC 7807 envelope and maps pipelex fields into the standard slots. Honors `disclosure_mode` by calling `to_dict(disclosure_mode)` internally. `request_id` lands as the `request_id` extension member. Returns a plain dict — pipelex stays HTTP-agnostic, no FastAPI/Starlette import.
- **RFC 7807 mapping table.** Standard slots get the *value* from the report; pipelex-native names are **dropped** from extensions to avoid a `title` collision and a `title`/`type` semantic split:

    | RFC 7807 standard slot | Source on `ErrorReport` | Note |
    |---|---|---|
    | `type` | `report.type_uri` | `type_uri` is removed from extension members |
    | `title` | `report.title` | `title` is removed from extension members (would otherwise duplicate the standard key) |
    | `status` | `report.http_status` | already a property |
    | `detail` | `report.message` (subject to disclosure-mode redaction) | the human-readable per-occurrence text |
    | `instance` | function argument | per-occurrence URN provided by caller |

    Extension members carry only the pipelex-native classification fields the standard does not cover: `error_type`, `error_domain`, `error_category`, `retryable`, `user_action`, `model`, `provider`, `provider_metadata`. `request_id` rides as an extension when the caller supplies one.
- **Tests:**
    - Parametrize across the three domains × two disclosure modes (six base cases). Assert INPUT passthrough; CONFIG/RUNTIME redaction-with-stable-identifiers-kept.
    - Parametrize `retryable: True | False | None` × `disclosure_mode: VERBOSE | STRICT`. Assert `retryable` survives both modes for all three values.
    - **INPUT-strict pin test:** an INPUT report whose `message` contains a path like `/Users/alice/secret.mthds` is returned **unchanged** in STRICT mode. Pin the documented contract.
    - RFC 7807 shape: `to_problem_document(instance="urn:p:123", request_id="r-1")` returns a dict with `type`, `title`, `status`, `detail`, `instance="urn:p:123"`, and a `request_id="r-1"` extension member.
    - **RFC 7807 mapping contract** (single test, two assertions):
        - Exactly one `title` key in the returned dict (no extension named `title`).
        - `result["type"] == report.type_uri` and `result["title"] == report.title`.
        - The extension members do not contain `type_uri` or `title` (they are mapped, not duplicated).
    - Verbose round-trip: `from_dict(report.to_dict(VERBOSE))` equals `report`.
    - Strict non-round-trip: `from_dict(report.to_dict(STRICT))` for a RUNTIME report has `message == "An internal error occurred."` and `provider is None`.
    - **Receiver-rehydration test:** simulate the API-side consumer. Take a populated `ErrorReport`, render `payload = {"status": "failed", "error": report.to_dict(VERBOSE)}`, then `ErrorReport.from_dict(payload["error"])` and assert it equals the original. Pins the contract pipelex-api will consume on the webhook.
- **Acceptance:** the API consumes both methods directly. The redaction rule and the envelope shape live exactly once in pipelex; no consumer duplicates them.

### [x] Item D-1 — Make `recover_error_report` total

- **Files:**
    - `pipelex/temporal/exceptions.py` — new subclass `UnrecoverableWorkflowFailureError(TemporalFlowError)` with `error_domain = ErrorDomain.RUNTIME` and `_declared_title = "Workflow failed without recoverable error details"`. Lives next to `TemporalFlowError`, `WorkflowExecutionError`, etc. (Reason: Temporal-flow-specific synthesis concept; locking it into the Temporal exceptions module keeps the base hierarchy clean.)
    - `pipelex/temporal/tprl/temporal_error.py` — `recover_error_report` signature becomes `def recover_error_report(exc: BaseException) -> ErrorReport`. When no embedded report is found or `from_dict` fails on version skew, synthesizes `UnrecoverableWorkflowFailureError(message_from_exc(exc)).to_error_report()`. `message_from_exc` extracts the most informative message available: the outer Temporal failure's message if non-empty, else `repr(exc)`.
    - `pipelex/temporal/tprl/workflow_caller.py` — call sites at `:128`, `:240`, `:292`: drop the `if error_report is not None` branches; the return is always usable.
- **Tests** (`tests/unit/pipelex/temporal/test_recover_error_report.py`):
    - Existing case `test_g3_malformed_details_recovers_nothing` becomes `test_g3_malformed_details_synthesizes_unrecoverable` and asserts the synthesized report has `error_type == "UnrecoverableWorkflowFailureError"`, `error_domain == "runtime"`, `retryable is None`, message contains the original exception message.
    - Existing case `test_g4_application_error_without_report_details_recovers_nothing` becomes `test_g4_application_error_without_report_details_synthesizes_unrecoverable` with the same assertions.
    - Existing case `test_no_application_error_in_chain_recovers_nothing` becomes `test_no_application_error_in_chain_synthesizes_unrecoverable`.
    - Existing positive cases continue to assert recovery of the packed report unchanged.
    - **New end-to-end pin (in `tests/unit/pipelex/temporal/test_workflow_caller_error_recovery.py`)** — a `WorkflowFailureError` that is NOT carrying an embedded `ErrorReport` (i.e., a non-Pipelex worker failure or a Temporal infra error) reaches `execute_workflow` and surfaces as a `WorkflowExecutionError` whose `.message` is the synthesized message (containing the underlying exception text), NOT the legacy `"Failed to execute workflow {workflow_class.__name__}"` framing. This pins the user-visible behavior change at the call site after the totality refactor: with the `if error_report is not None` branch dropped, the unrecoverable path no longer produces the Pipelex-framed fallback string. The test should also assert `WorkflowExecutionError.error_report is not None` and `error_report.error_type == "UnrecoverableWorkflowFailureError"`.
- **Note on no-longer-reached paths in existing tests.** After this change, `WorkflowExecutionError(msg)` without `error_report=...` is still reachable via `start_workflow` (which only catches `WorkflowAlreadyStartedError` / `RPCError`, not `WorkflowFailureError`) and the `WorkflowAlreadyStartedError` / `RPCError` branches of `execute_workflow`. The existing unit tests `test_g7_to_error_report_falls_through_to_cause_enrichment_when_no_report` and `test_to_error_report_is_generic_without_report_or_pipelex_cause` continue to exercise that defensive API path — do NOT remove them as "dead code" during D-1 implementation; they still cover the non-`WorkflowFailureError` branches.
- **Acceptance:** callers never see `None` from this function. The "hand-author a fallback report" pattern the original spec proposed (see [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §D) is eliminated — there is exactly one place that constructs the unrecoverable report. The user-visible `WorkflowExecutionError.message` on the unrecoverable path changes from the Pipelex-framed `"Failed to execute workflow X"` to the synthesized `message_from_exc(exc)` — this is intentional (more diagnostic) and pinned by the new end-to-end test above.

**Checkpoint 2 — End of Stage 2** ⬇ See [Checkpoint 2 brief](#checkpoint-2--end-of-stage-2) below.

---

## Stage 3 — Async error pipe *(unblocks `pipelex-api` Phase 4 — most important item)*

### [x] Item D-2 — Thread `ErrorReport` to the webhook

- **Prereq: convert `ErrorReport` from `@pydantic.dataclasses.dataclass` to `BaseModel`.**

    ```python
    class ErrorReport(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

        error_type: str
        message: str
        title: str         # required after Item A
        type_uri: str      # required after Item A
        error_category: str | None = None
        error_domain: str | None = None
        retryable: bool | None = None
        user_action: UserAction | None = None
        model: str | None = None
        provider: str | None = None
        provider_metadata: ProviderErrorMetadata | None = None
    ```

    `to_dict` becomes `self.model_dump(exclude_none=True)` (plus disclosure-mode redaction from Item C). `from_dict` becomes `cls.model_validate(data)`. The existing `BaseModelPayloadConverter` (`pipelex/temporal/temporal_data_converter.py:54`) already handles `BaseModel` and `BaseModel | None` — no converter or kajson surgery.

    **Why this over extending the data converter for Pydantic dataclasses:** one type to convert; smaller diff; the BaseModel form is what kajson and the data converter were built for. The "generic Pydantic dataclass support" framing was speculative future-proofing for a use case that does not yet exist.

- **Files:**
    - `pipelex/base_exceptions.py` — the `BaseModel` conversion above.
    - `pipelex/pipeline/exceptions.py` — **breaks under the BaseModel conversion.** Currently uses `from dataclasses import replace` and `replace(report, error_domain=..., user_action=...)` at `pipeline/exceptions.py:1` and `:44`. After the conversion, this raises at runtime (`replace()` is stdlib-dataclass-only; BaseModel has `model_copy(update={...})`). Migration: drop the `from dataclasses import replace` import and rewrite the call as `report.model_copy(update={"error_domain": ..., "user_action": ...})`. **This must land in the same PR as the BaseModel conversion** — every `PipelineExecutionError.to_error_report()` call breaks without it. Add a regression test (`tests/unit/pipelex/pipeline/test_exceptions.py` or extend `test_base_exceptions.py`) that constructs a `PipelineExecutionError` with no enriching cause, calls `to_error_report()`, and asserts the resulting `error_domain == ErrorDomain.RUNTIME` and `user_action.kind == UserActionKind.UNKNOWN`. Without this test, the converter swap would break the floor behavior silently.
    - `pipelex/pipe_run/delivery_executor.py` — `execute(...)` and `_notify_webhook(...)` accept `error_report: ErrorReport | None = None`. When `status == FAILED` and `error_report is not None`, the webhook payload includes `error = error_report.to_dict(DisclosureMode.VERBOSE)`. The API can choose strict mode at its own HTTP surface.
    - `pipelex/temporal/tprl_pipe/act_deliver.py` — `DeliveryActivityArg` gains `error_report: ErrorReport | None = None`. No `_dict` shim — the data converter handles `BaseModel | None` directly.
    - `pipelex/temporal/tprl_pipe/wf_pipe_run.py` — on the `ChildWorkflowError` catch, call `error_report = recover_error_report(exc.cause)` (total — always a value, see Item D-1). Pass it into `DeliveryActivityArg`.
- **Tests:**
    - `tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py` — add a case that round-trips an `ErrorReport` carrying populated `user_action` and `provider_metadata` (nested BaseModels) through a workflow→activity hop. **This must land before** the activity arg is changed.
    - `tests/unit/pipelex/pipe_run/test_delivery_executor.py` — webhook payload includes `error = report.to_dict(VERBOSE)` on `FAILED` with non-`None` report; absent on `COMPLETED` or `None` report. Round-trips a realistic `ErrorReport` with `provider_metadata` populated.
    - `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` — **two extensions** that lock in the fix for the outer-wrap concern:
        1. Existing `WfPipeRouter` case continues to assert recovered classification on the submitter side.
        2. **New `WfPipeRun` end-to-end case** that dispatches `WfPipeRun` (not `WfPipeRouter`) with a `delivery_assignment` whose webhook points at an in-process httpx mock transport (`httpx.MockTransport`). Asserts:
            - The webhook receiver was called once with `status == "failed"`.
            - The webhook payload includes `error = <dict>` with the full classification (`error_type`, `error_category`, `retryable`, `user_action`, `model`, `provider`, `title`, `type_uri`).
            - The submitter-side `WorkflowExecutionError.to_error_report()` carries the same classification (i.e. the outer Temporal wrap does NOT drop the inner report).
        3. A second new `WfPipeRun` case **without** a `delivery_assignment` — verifies the submitter-side path still surfaces classification even when delivery isn't configured.
- **Acceptance:** a Temporal-side pipe failure reaches the webhook with the same classification a sync caller would see locally. No silent loss of fields across activity → workflow (child) → workflow (parent) → delivery → submitter.

**Checkpoint 3 — End of Stage 3 (largest unlock; recommended stopping point if context is tight)** ⬇ See [Checkpoint 3 brief](#checkpoint-3--end-of-stage-3) below.

---

## Stage 4 — DX polish *(pairs with `pipelex-api` Phase 5)*

### [ ] Item E — Per-class `type` URI doc pages *(spec item 7)*

- **Files:** `docs/` (mkdocs) + a `pipelex-dev` CLI subcommand `generate-error-pages`.
- **Generator:** a `pipelex-dev` CLI subcommand (consistent with the existing `generate-mthds-schema`, `refresh-graph-ui-sri` subcommands) that walks `PipelexError.__subclasses__()` recursively and emits one page per class under `docs/errors/<kebab>.md`. Page content: class name, `cls.title()`, `cls.error_domain`, typical `user_action` (if declared at class level), link to parent class doc, back-link to the schema page.
- **Authors override per-class content where it adds value** by hand-editing the generated page; the generator detects an `<!-- gstack:authored -->` marker and skips regeneration of that page.
- **Tests:** unit smoke test that runs the generator against the current hierarchy and asserts (a) no exceptions, (b) one page per non-abstract `PipelexError` subclass, (c) kebab slugs match `pascal_case_to_kebab(cls.__name__)`. (The uniqueness guard from Item A's tests already catches collisions.)
- **Acceptance:** clicking a `type` URI from a real error response lands on a populated page. Adding a new `PipelexError` subclass produces a new doc page automatically on next `pipelex-dev generate-error-pages` run.

**Checkpoint 4 — End of Stage 4 (final stage)** ⬇ See [Checkpoint 4 brief](#checkpoint-4--end-of-stage-4) below.

---

## What we dropped from the original spec

| Spec item | Status |
|---|---|
| Item 8 — `query_pipeline_state(...)` | **Dropped.** Speculative future work; no current consumer needs it. Repo CLAUDE.md: *"Don't design for hypothetical future requirements."* Will be revisited when the first consumer materializes with concrete requirements. |
| Item 9 — full-payload webhook signature | **Split out.** Lives at [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md). It is security work, not error-handling — the trust-topology shift (from dispatcher-side signing to worker-side signing) deserves its own review on security merit, and its cross-repo deploy sequence is independent of this plan's. |

See [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) for the full reasoning on this and the consolidations above.

---

## Deferred follow-ups (out of scope for this pass)

Tracked here so the idea doesn't get lost. Each lands when a concrete consumer materializes with requirements.

### Cause-chain serialization on `ErrorReport`

**What.** Add `causes: list[CauseEntry] | None = None` to `ErrorReport`, where each `CauseEntry` carries the identity triplet (`error_type`, `title`, `type_uri`, `message`) of one wrapper layer. `_enrich_error_report_from_cause` already walks `__cause__`; it would also collect entries during the walk.

**Why deferred.** The current flat model satisfies the API-readiness plan: classification fields (`error_category`, `provider`, `retryable`, etc.) already backfill from the cause, which is what consumers need for routing decisions. The cause chain adds Sentry-style debug richness — valuable when a concrete consumer asks for it, speculative without one.

**Why this is additive, not a future refactor.** Every item in this `TODOS.md` stays unchanged when `causes` later lands:

- `title()` / `type_uri()` classmethods (Item A) — unchanged.
- `recover_error_report` totality (Item D-1) — unchanged.
- Webhook threading (Item D-2) — unchanged; carries a richer dict.
- Webhook signing (separate security track) — unchanged; signs whatever body bytes are there.
- Disclosure-mode redaction (Item C) — extended by adding per-entry redaction to the existing rule, not rewritten.
- Temporal data converter — unchanged (`BaseModel` round-trips already work).

`extra="forbid"` plus `exclude_none=True` in `to_dict` mean old payloads validate without the new field.

**Triggers for picking it up.** Any of: (a) the CLI gains a verbose error mode operators want for debugging; (b) the API exposes a `?verbose=true` query param or `Accept-Profile` header; (c) a log-shipper consumer requests Sentry-compatible chain output.

---

## Tracking

| ID | Item | Stage | Status |
|---|---|---|---|
| A | `PipelexError.title()` + `type_uri()` with auto-derive *(spec 1+2)* | 1 | [x] |
| B | `request_id` on `JobMetadata` *(spec 3)* | 1 | [x] |
| C | `to_dict(disclosure_mode=)` + `to_problem_document(...)` *(spec 4+6)* | 2 | [x] |
| D-1 | Total `recover_error_report` | 2 | [x] |
| D-2 | `ErrorReport` → `BaseModel`; thread to webhook; full `WfPipeRun` chain test *(spec 5)* | 3 | [x] |
| E | Per-class doc pages *(spec 7)* | 4 | [ ] |

The original spec's item 9 (webhook signature) is tracked separately at [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md).

---

## Checkpoints

Each checkpoint **must** end with: (a) all checkboxes in that stage checked, (b) `make agent-check` clean, (c) `make agent-test` clean, (d) this section updated with concrete file:line references for what landed, (e) any deviations from the plan recorded in [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md), (f) cold-start instructions confirmed for the next session.

Checkpoints are **hard stops**. Do not pick up the next stage in the same session — context will have grown and the next session is cheaper to start fresh.

### Checkpoint 1 — End of Stage 1

**What should be true:**
- `PipelexError` has `_declared_title` / `_declared_type_uri` ClassVars + `title()` / `type_uri()` classmethods with auto-derive defaults.
- `ErrorReport` carries **required `str`** `title` and `type_uri` fields; round-trip through `model_dump` / `model_validate` preserves them. (`ErrorReport` still `@dataclass` at this stage — `BaseModel` conversion lands in Stage 3.)
- `pascal_case_to_kebab` helper exists in `pipelex/tools/misc/string_utils.py`.
- `get_config().pipelex.errors_config.base_uri` exists, defaulting to `"https://pipelex.dev/errors"`.
- Curated `_declared_title` overrides for `CogtError`, `EnvVarNotFoundError`, and any other class whose auto-derive reads badly.
- `JobMetadata.request_id` exists; `pipeline_run_setup(...)` accepts it; an integration test demonstrates it riding the wire to the activity.
- Class-name uniqueness test passes for the current hierarchy.
- All new tests exist and pass; `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**

- **Curated `_declared_title` overrides landed:**
    - `PipelexError._declared_title = "Pipelex error"` — set directly in the class body. Inheritance is bypassed in `title()` via `cls.__dict__.get(...)` (which only consults the requesting class's *own* attribute dict, never walking the MRO), so subclasses without an explicit `_declared_title` of their own auto-derive from their own class name rather than inheriting `"Pipelex error"`.
    - `PipelexUnexpectedError._declared_title = "Unexpected internal error"`
    - `SecurityError._declared_title = "Security policy violation"`
    - `CogtError._declared_title = "AI inference failed"`
    - `EnvVarNotFoundError._declared_title = "Environment variable not set"`
    - `ToolError._declared_title = "Tool error"`
    - `CredentialsError._declared_title = "Missing or invalid credentials"`
    - `FatalError._declared_title = "Fatal error"`
    - `TomlError._declared_title = "TOML parse error"`
    - `StorageError._declared_title = "Storage error"`
    - `StorageS3Error._declared_title = "S3 storage error"` (auto-derive was broken: `pascal_case_to_sentence("StorageS3")` drops the `S` and produced `"Storage 3"`)
    - `StuffError._declared_title = "Stuff error"`
    - `ConceptError._declared_title = "Concept error"`
    - `LibraryError._declared_title = "Library error"`
- **Files touched:**
    - Production:
        - `pipelex/base_exceptions.py` — added `_humanize_class_name`, `_declared_title` / `_declared_type_uri` ClassVars, `title()` / `type_uri()` classmethods, required `title` / `type_uri` fields on `ErrorReport`, propagation in `to_error_report()` / `_enrich_error_report_from_cause()`. `type_uri()` reads the base URI from the `ErrorManager` singleton (see deviation below).
        - `pipelex/errors/error_manager.py` — new `ErrorManager` singleton (built on `ABCSingletonMeta` / `MetaSingleton`) holding the `ErrorsConfig`. Mirrors the `GraphTracerManager` precedent so `base_exceptions.py` can read it without importing `pipelex.hub`. Types its constructor against a local structural `Protocol` so this module retains zero transitive dependency on the config layer (avoids re-entering `pipelex.base_exceptions` via `pipelex.system.exceptions`).
        - `pipelex/errors/errors_config.py` — new home for the `ErrorsConfig(ConfigModel)` model (moved out of `pipelex/system/configuration/configs.py` so it lives next to the manager that consumes it). `configs.py` now imports it and still mounts it under `Pipelex.errors_config`.
        - `pipelex/pipelex.py` — constructs `self.error_manager = ErrorManager(errors_config=get_config().pipelex.errors_config)` right after config loads; `teardown()` calls `ErrorManager.clear_instance()`.
        - `pipelex/system/configuration/configs.py` — added `ErrorsConfig(ConfigModel)` mounted under `Pipelex.errors_config`.
        - `pipelex/pipelex.toml` — `[pipelex.errors_config]` section with `base_uri = "https://pipelex.dev/errors"`.
        - `pipelex/tools/misc/string_utils.py` — added `pascal_case_to_kebab` (acronym-aware: splits on `[a-z0-9] -> [A-Z]` and `[A-Z] -> [A-Z][a-z]` transitions; does NOT reuse `pascal_case_to_sentence` which has token-loss bugs around digit boundaries).
        - `pipelex/cogt/exceptions.py:87-99` — `CogtError.to_error_report()` populates `title` / `type_uri`.
        - `pipelex/pipeline/job_metadata.py` — added `request_id: str | None = None` to `JobMetadata` (docstring distinguishes from `ProviderErrorMetadata.request_id`).
        - `pipelex/pipeline/pipeline_run_setup.py` — `request_id` kwarg threaded into the constructed `JobMetadata`.
        - `pipelex/temporal/log_temporal.py` — every `WorkflowLog` / `ActivityLog` method takes optional `request_id: str | None = None`, forwarded to the Temporal logger via `extra={"request_id": ...}`.
        - Curated `_declared_title` overrides in: `pipelex/cogt/exceptions.py`, `pipelex/system/exceptions.py`, `pipelex/system/environment.py`, `pipelex/tools/misc/toml_utils.py`, `pipelex/tools/storage/exceptions.py`, `pipelex/core/stuffs/exceptions.py`, `pipelex/core/concepts/exceptions.py`, `pipelex/libraries/exceptions.py`.
    - Tests:
        - New: `tests/helpers/error_report.py` (helper for non-serialization tests), `tests/unit/pipelex/test_pipelex_error_title_and_type_uri.py`, `tests/unit/pipelex/test_pipelex_error_type_uri_uniqueness.py`, `tests/unit/pipelex/pipeline/test_job_metadata_request_id.py`, `tests/integration/pipelex/pipeline/test_pipeline_run_setup_request_id.py`.
        - Updated: `tests/unit/pipelex/test_base_exceptions.py` (cold-import test — drops `to_error_report()` line and inlines literal `title` / `type_uri`), `tests/unit/pipelex/test_error_report_from_dict.py` (real values + missing-required-field cases for `title` / `type_uri`), `tests/unit/pipelex/test_error_http_status.py` + `tests/unit/pipelex/exceptions/test_error_domain.py` (helper-based), `tests/unit/pipelex/cogt/test_exceptions.py` (expected dict includes new fields), `tests/unit/pipelex/tools/misc/test_string_utils.py` (parametrized `pascal_case_to_kebab` table), `_FULL_REPORT` fixtures in the four temporal tests.
- **Surprises / deviations (record in `api-companion-revisions.md`):**
    1. **`type_uri()` reads from an `ErrorManager` singleton (`pipelex/errors/error_manager.py`) constructed by Pipelex bootstrap**, not from `get_config().pipelex.errors_config.base_uri` directly. Original plan called for the lazy `from pipelex.config import get_config` inside `type_uri()`, but pyright reported the static cycle on chain-entry-point files (`pipelex/__init__.py` etc.) that a file-level pragma on `base_exceptions.py` could not suppress. The `ErrorManager` mirrors the `GraphTracerManager` pattern (`MetaSingleton`-based, not registered on `pipelex.hub`), keeping `pipelex.base_exceptions` at the bottom of the import graph (no cycle at all). The manager holds the full `ErrorsConfig` instance — moved into its own module `pipelex/errors/errors_config.py` — typed structurally via a local `Protocol` in `error_manager.py` so the manager itself takes zero dependency on `ConfigModel` (which would re-introduce the cycle through `pipelex.system.exceptions`). Locked-in behavior preserved: no fallback constant; calling `type_uri()` before bootstrap raises a clear `RuntimeError`.
    2. **`_declared_title` inheritance is intentionally bypassed in `title()`** via `cls.__dict__.get("_declared_title")` rather than direct attribute access. Without this, every bare subclass of `PipelexError` would inherit `"Pipelex error"` instead of auto-deriving from its own class name. The locked-in semantics ("class either declares its own title or auto-derives from its own name") is pinned by a dedicated test (`test_declared_title_does_not_leak_through_inheritance`).
    3. **`pascal_case_to_kebab` is a fresh regex-based implementation, NOT `pascal_case_to_sentence(...).lower().replace(" ", "-")`.** The existing `pascal_case_to_sentence` loses single-letter tokens before digits (`StorageS3` -> `"Storage 3"`, `V2API` -> `"2 api"`) which would silently mangle docs URIs. `pascal_case_to_kebab` splits on the standard PascalCase boundaries and preserves every character.
    4. **`StorageS3Error` got a curated `_declared_title = "S3 storage error"`** because the auto-derive (via the existing buggy `pascal_case_to_sentence`) would have produced `"Storage 3"`. Documented as a curated override rather than fixing the underlying `pascal_case_to_sentence` bug (out of scope).
    5. **`tests/unit/pipelex/test_base_exceptions.py` was kept with just the cold-import subprocess test** (1 TestClass per module rule); the `TestPipelexErrorTitleAndTypeUri` and `TestPipelexErrorTypeUriUniqueness` classes live in their own new files.

**Cold-start for Checkpoint 2:**

- Re-read items C + D-1 here, and [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §C + §D.
- Skim `pipelex/temporal/tprl/temporal_error.py:recover_error_report` and its three call sites in `workflow_caller.py`.
- Run `git log --oneline -20` and `make agent-test` to confirm starting clean.
- Note: `ErrorReport` is still a `@dataclass` at the end of Stage 1; Stage 3's Item D-2 converts it to `BaseModel`. The Stage 2 work on `to_dict(disclosure_mode=...)` / `to_problem_document(...)` lands on the dataclass form.

---

### Checkpoint 2 — End of Stage 2

**What should be true:**
- `DisclosureMode` enum in `pipelex/base_exceptions.py`.
- `ErrorReport.to_dict(disclosure_mode=...)` and `ErrorReport.to_problem_document(...)` exist and behave per the redaction rule (stable identifiers kept, message redacted for CONFIG/RUNTIME, INPUT passthrough).
- Verbose round-trip preserved; strict round-trip explicitly documented as lossy.
- `recover_error_report` is total: `BaseException -> ErrorReport`. `UnrecoverableWorkflowFailureError` lives in `pipelex/temporal/exceptions.py`. All three call sites in `workflow_caller.py` are simplified.
- `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**

- **Files touched:**
    - Production:
        - `pipelex/base_exceptions.py` — added `DisclosureMode` enum (VERBOSE / STRICT) with the path-leak-shield-vs-classification-projection contract documented on its docstring; added `_INTERNAL_ERROR_PLACEHOLDER` / `_STRICT_KEPT_FIELDS` module-level constants so `to_dict` and the RFC 7807 extension projection stay in sync; added `disclosure_mode` parameter on `to_dict` (default VERBOSE) implementing the INPUT-passthrough + CONFIG/RUNTIME redaction rule; added `to_problem_document(*, instance=None, request_id=None, disclosure_mode=DisclosureMode.VERBOSE)` mapping `type_uri → type` / `title → title` / `http_status → status` / `message → detail` (no extension echoes, exactly one `title` key).
        - `pipelex/temporal/exceptions.py` — added `UnrecoverableWorkflowFailureError(TemporalFlowError)` with `error_domain = ErrorDomain.RUNTIME` and `_declared_title = "Workflow failed without recoverable error details"`.
        - `pipelex/temporal/tprl/temporal_error.py` — `recover_error_report` signature changed to `(BaseException) -> ErrorReport` (total — no more `| None`). When no embedded report is found or `from_dict` fails on version skew, synthesizes `UnrecoverableWorkflowFailureError(_message_from_exc(exc)).to_error_report()`. New private `_message_from_exc` helper walks the `__cause__` chain for the deepest non-empty message (preserving worker-side cause text), falling back to `repr(exc)` only when every node in the chain has an empty message.
        - `pipelex/temporal/tprl/workflow_caller.py` — dropped the `if error_report is not None` branches at three call sites: `execute_workflow`'s `WorkflowFailureError` clause (was `:128`), and the `isinstance(exc.cause, ApplicationError)` branches of `execute_child_workflow` (`:240`) and `start_child_workflow` (`:292`). The `recover_error_report` return is always usable now. The defensive `WorkflowExecutionError(msg)` constructions on the `WorkflowAlreadyStartedError` / `RPCError` / non-`ApplicationError`-cause paths are intentionally retained — those branches do NOT call `recover_error_report`.
    - Tests:
        - New: `tests/unit/pipelex/test_error_report_disclosure_mode.py` (`TestErrorReportDisclosureMode` — INPUT-passthrough pin, CONFIG/RUNTIME redaction, retryable survival across modes, verbose round-trip, strict non-round-trip, receiver-rehydration). `tests/unit/pipelex/test_error_report_problem_document.py` (`TestErrorReportProblemDocument` — standard-slot population, no `title`/`type_uri` extension duplication, single-`title`-key contract, `request_id` / `instance` extension optionality, strict-mode redaction passthrough for INPUT).
        - Updated: `tests/unit/pipelex/temporal/test_recover_error_report.py` — G3 / G4 / no-application-error cases renamed to `*_synthesizes_unrecoverable` and assert the synthesized report's `error_type` / `error_domain` / `retryable` / message contents instead of `is None`. `tests/unit/pipelex/temporal/test_workflow_caller_error_recovery.py` — `test_workflow_failure_without_report_stays_generic` renamed to `*_synthesizes_unrecoverable` with the round-3 P2 pin: assertion that the synthesized `error.message` contains the underlying exception text and is NOT the legacy `"Failed to execute workflow X"` framing. `tests/unit/pipelex/temporal/test_workflow_caller_child_error_recovery.py` — G3 / G4 child cases renamed and updated to assert the synthesized unrecoverable report; the non-`ApplicationError`-cause case stays unchanged.
- **Surprises / deviations (record in `api-companion-revisions.md`):**
    1. **`_message_from_exc` walks the full `__cause__` chain for the deepest non-empty message, NOT just `str(exc) or repr(exc)`.** The plan suggested literally "outer Temporal failure's message if non-empty, else `repr(exc)`", but `WorkflowFailureError` always carries the generic outer text `"Workflow execution failed"`, which would not satisfy the round-3 P2 pin (test asserts the synthesized message "contains the underlying exception text"). The implementation walks the chain keeping the deepest non-empty message — so `WorkflowFailureError(cause=RuntimeError("worker crashed hard"))` synthesizes a message containing `"worker crashed hard"`, not the generic outer framing. `repr(exc)` remains the final fallback when every node's `str` is empty.
    2. **All three call sites in `workflow_caller.py` were simplified, not just the submitter-side one at `:128`.** The plan's "three call sites" list (`:128`, `:240`, `:292`) is now uniformly post-`if error_report is not None` removal. The child-workflow paths' G3 / G4 tests in `test_workflow_caller_child_error_recovery.py` were updated to match.
    3. **Pre-existing unrelated test failure flagged for the next session:** `tests/e2e/agent_cli/test_offline_run_dry.py::TestOfflineDryRun::test_gateway_no_cache_no_network_fails_with_unavailable` fails identically on baseline (`git stash` rerun confirms). The CLI subprocess returns an empty `{}` JSON payload while the assertion expects `error_type == "RemoteConfigUnavailableError"`. NOT introduced by Stage 2 — should be fixed independently.

**Cold-start for Checkpoint 3:**

- Re-read Item D-2 + [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §D. This is the load-bearing stage.
- The `BaseModel` conversion is the gate — land the round-trip test before the activity arg change.
- Confirm the new `WfPipeRun` end-to-end test is in scope, not deferred. The existing test bypasses `WfPipeRun`; the new test is the safety net for the outer Temporal wrap.
- `recover_error_report` is already total (Item D-1) — Item D-2's `wf_pipe_run` change to `error_report = recover_error_report(exc.cause)` does NOT need a `None` guard.
- The pre-existing `test_gateway_no_cache_no_network_fails_with_unavailable` failure on baseline is unrelated to the error-handling refactor — fix or skip independently before the next `make agent-test` gate.

---

### Checkpoint 3 — End of Stage 3

**Biggest unlock; strong stopping point.** After this, the API team can build Phase 4 against a lossless contract.

**What should be true:**
- `ErrorReport` is now a `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`. Round-trip test passes.
- `DeliveryActivityArg.error_report: ErrorReport | None` (no `_dict` shim).
- `DeliveryExecutor.execute(error_report=...)` and `_notify_webhook(error_report=...)` write `payload["error"] = error_report.to_dict(VERBOSE)` on `FAILED`.
- `wf_pipe_run` recovers the report via total `recover_error_report(exc.cause)` and threads it through.
- **Full `WfPipeRun` end-to-end test** demonstrates classification (`error_type`, `error_category`, `retryable`, `user_action`, `model`, `provider`, `title`, `type_uri`) surviving from a worker-side `CogtError` all the way to BOTH (a) the webhook payload AND (b) the submitter-side `WorkflowExecutionError.to_error_report()`. The outer Temporal wrap does not drop the inner report.
- `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**

- **Files touched:**
    - Production:
        - `pipelex/base_exceptions.py` — `ErrorReport` is now a `BaseModel(model_config=ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True))`. `to_dict` uses `self.model_dump(exclude_none=True)` directly; `from_dict` uses `cls.model_validate(data)`. Dropped the cached `_ERROR_REPORT_ADAPTER` (no longer needed — `model_dump`/`model_validate` are first-class on BaseModel). Dropped the `pydantic.dataclasses` and `TypeAdapter`/`cast` imports.
        - `pipelex/pipeline/exceptions.py` — `PipelineExecutionError.to_error_report()` uses `report.model_copy(update={...})` instead of `dataclasses.replace(report, ...)`. Removed the `from dataclasses import replace` import.
        - `pipelex/temporal/tprl/temporal_error.py` — `recover_error_report` uses `set(ErrorReport.model_fields)` instead of `{field.name for field in fields(ErrorReport)}`. Removed the `from dataclasses import fields` import.
        - `pipelex/pipe_run/delivery_executor.py` — `execute(...)` and `_notify_webhook(...)` accept `error_report: ErrorReport | None = None`. When non-None, the webhook payload includes `error = error_report.to_dict(DisclosureMode.VERBOSE)` so the receiver can losslessly rehydrate via `ErrorReport.from_dict`. Imports `DisclosureMode` and `ErrorReport`.
        - `pipelex/pipe_run/pipe_run.py` — direct-mode `PipeRun.run` now captures `error_report = exc.to_error_report()` when the caught exception is a `PipelexError` and threads it into `self._delivery_executor.execute(error_report=...)`. Non-Pipelex exceptions surface no report (the in-process semantics consumers already expect).
        - `pipelex/temporal/tprl_pipe/act_deliver.py` — `DeliveryActivityArg` gains `error_report: ErrorReport | None = None`. The `act_deliver` activity forwards it to `DeliveryExecutor.execute(error_report=...)`. The existing `BaseModelPayloadConverter._unwrap_optional_base_model` handles the `ErrorReport | None` field directly — no shim needed.
        - `pipelex/temporal/tprl_pipe/wf_pipe_run.py` — on the `ChildWorkflowError` catch path, calls `recover_error_report(exc.cause if exc.cause is not None else exc)` (total since Item D-1), constructs `WorkflowExecutionError("WfPipeRouter failed", error_report=error_report)`, and threads the same `error_report` into `DeliveryActivityArg`. The `ErrorReport` import sits inside the `imports_passed_through()` block with a `noqa: TC001` because the workflow sandbox needs it at runtime for the local-variable annotation.
    - Tests:
        - New: `tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py::TestPayloadCodecRoundTrip::test_error_report_round_trips_through_activity` — pre-flight that pins the `ErrorReport` BaseModel round-trip through a workflow→activity hop with populated nested `UserAction` / `ProviderErrorMetadata`. Lands before the activity arg change in the same commit; safety-net for the `BaseModelPayloadConverter` carrying the new arg.
        - New: `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py::TestWorkflowErrorReportFullChain::test_wf_pipe_run_failure_threads_error_report_to_webhook_and_submitter` — end-to-end `WfPipeRun` chain with `delivery_assignment` whose webhook is intercepted by an `httpx.AsyncClient` mock (via `mocker.AsyncMock(side_effect=...)`). Asserts both (a) the webhook payload's `error` dict carries the full classification (`error_type` / `error_category` / `retryable` / `model` / `provider` / `title` / `type_uri` / `user_action.kind`) and (b) the submitter-side `WorkflowExecutionError.to_error_report()` carries the same classification — i.e. the outer Temporal wrap did NOT drop the inner report.
        - New: `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py::TestWorkflowErrorReportFullChain::test_wf_pipe_run_failure_without_delivery_assignment_surfaces_classification` — verifies the submitter-side path still surfaces classification when no `delivery_assignment` is configured (skips `act_deliver` entirely).
        - New: `tests/unit/pipelex/pipe_run/test_delivery_executor.py::TestDeliveryExecutor::test_webhook_includes_error_report_on_failed_status` + `test_webhook_omits_error_when_report_is_none` — receiver-rehydration pin (`ErrorReport.from_dict(payload["error"]) == original`) and the COMPLETED-without-report contract.
        - Updated: `tests/unit/pipelex/cogt/test_exceptions.py::TestErrorCategoryInfrastructure::test_error_report_is_frozen` — now expects `pydantic.ValidationError` instead of `dataclasses.FrozenInstanceError`. Updated the test module's imports accordingly.
- **Workflow's "preserve execution_error for failure attribution" reordering still holds.** `wf_pipe_run.py` re-raises in order: `if execution_error is not None: raise execution_error` first, `if delivery_error is not None: raise delivery_error` second. Test `tests/integration/pipelex/temporal/test_wf_pipe_run_failure_path.py::TestWfPipeRunFailurePath` continues to pin the failure-path invariant (router failure fires delivery with FAILED status before re-raising), and the new full-chain test pins the additional invariant that the structured report is recovered AND threaded through delivery before the re-raise.
- **Surprises / deviations (recorded in `api-companion-revisions.md` §D-2):**
    1. **The direct-mode `PipeRun` path also threads `error_report`** (not just the Temporal path the plan called out). The plan's D-2 acceptance criterion ("a Temporal-side pipe failure reaches the webhook with the same classification a sync caller would see locally") implies parity, so the local executor was updated to call `exc.to_error_report()` when the caught exception is a `PipelexError` and pass it to `DeliveryExecutor.execute`. Non-`PipelexError` exceptions still surface no report (consistent with the in-process semantics consumers already expect).
    2. **`temporal_error.py` field-introspection swap.** `recover_error_report`'s known-fields set was built via `{field.name for field in fields(ErrorReport)}` (stdlib-dataclasses-only API). Under the BaseModel conversion this would `AttributeError` at runtime. Swapped to `set(ErrorReport.model_fields)`, which is the Pydantic v2 equivalent and is iterable as a `dict[str, FieldInfo]` keyed by field name.
    3. **`title` auto-derive in the full-chain test.** The new `WfPipeRun` end-to-end test asserts `error_dict["title"] == "Llm completion"`, not `"AI inference failed"`. The `_declared_title` inheritance-bypass rule (locked in at Checkpoint 1) means `LLMCompletionError.title()` does NOT inherit `CogtError._declared_title`; it auto-derives from its own class name. Documented inline in the test alongside the assertion so a future reader sees why.
    4. **Pre-existing baseline test failure persists.** `tests/e2e/agent_cli/test_offline_run_dry.py::TestOfflineDryRun::test_gateway_no_cache_no_network_fails_with_unavailable` still fails on `feature/API-readiness` for unrelated reasons (CLI subprocess returns empty `{}` instead of `{"error_type": "RemoteConfigUnavailableError"}`). Confirmed identical failure on `git stash` baseline — NOT introduced by Stage 3 and not in scope for this checkpoint. Tracked here for the Checkpoint 4 cold-start (or earlier, independent fix) per the Checkpoint 2 hand-off note.
- **Notify the API team** that Stages 1–3 are landed and their Phases 0/1/4 are unblocked. Update [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) "current state" section.

**Cold-start for Checkpoint 4:**

- Stage 4 is docs polish. Re-read Item E.
- Read `docs/under-the-hood/error-model.md` to understand the docs site layout.
- Confirm docs build cleanly locally before starting.
- The pre-existing `test_gateway_no_cache_no_network_fails_with_unavailable` failure on baseline carries over from Checkpoint 2 — fix or skip independently before the next `make agent-test` gate.

---

### Checkpoint 4 — End of Stage 4

**What should be true:**
- `pipelex-dev generate-error-pages` emits one page per non-abstract `PipelexError` subclass under `docs/errors/<kebab>.md`.
- A few high-traffic classes have authored overrides (marked with `<!-- gstack:authored -->`); the rest use the generated default and look sensible.
- mkdocs build clean; `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Generator location + invocation: _TBD_
- Authored pages list: _TBD_
- Files touched: _TBD_

**Post-completion (end of error-handling refactor):**
- Mark [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) "current state" section as fully landed.
- Replace this `TODOS.md` with a short pointer to the merged PRs.
- The webhook-signing security track ([`wip/security/webhook-signing.md`](wip/security/webhook-signing.md)) is independent and can land on its own schedule.

---

## Where to look when starting cold

1. This `TODOS.md` — find the first unchecked item and its checkpoint context. **Read the "Decisions locked in" section at the top first** — the items below assume them.
2. [`wip/error-handling/api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) — what we are actually building vs. what the original spec proposed, with rationale per item. **The pipelex-api agent reads this to know what to expect.**
3. [`wip/error-handling/changes-for-api-early-draft.md`](wip/error-handling/changes-for-api-early-draft.md) — the original spec, kept for context but superseded by the revisions doc.
4. [`wip/error-handling/README.md`](wip/error-handling/README.md) — the broader error-handling landscape.
5. The most recent checkpoint's "Fill in at checkpoint time" block — running notes from the previous session.
6. `git log --oneline -20` to see the most recent landings.

The cross-repo counterpart lives in [`../pipelex-api/wip/error-handling/`](../../pipelex-api/wip/error-handling/) — open it side-by-side when reasoning about item D-2. The webhook-signing security track has its own plan at [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md).

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 3 | CLEAR (PLAN) | Round 1: 12 issues / 2 critical gaps (folded). Round 2: 1 P1 + 1 P2 (folded). Round 3: 1 P1 + 2 P2 (folded). |
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | n/a | not applicable (library plan) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**UNRESOLVED:** none.

**Decisions resolved across review rounds:**
- Cause-enrichment policy: **wrapper-wins** for `title`/`type_uri`. Cause-chain serialization deferred (see "Deferred follow-ups" section).
- `WorkflowExecutionError` is the single **wrapper-loses** carve-out — preserves recovered inner classification across the Temporal serialization boundary. Documented in "Decisions locked in" above.
- Webhook signing secret source: **env-only** (`PIPELEX_WEBHOOK_SIGNING_SECRET`). No config field. Per the repo policy that no secrets live in committed config.
- Item F (webhook signing) **split out** of this plan into [`wip/security/webhook-signing.md`](wip/security/webhook-signing.md). The findings A3 (rollout) and A5 (env-vs-config) move with it.
- `DisclosureMode.STRICT` documented on its own docstring as a classification-projection, NOT a path-leak shield. INPUT-domain reports pass through unchanged in STRICT mode; the contract is pinned in the enum's docstring at the entry point developers read.

**VERDICT:** ENG REVIEW (3 rounds) — issues folded into the plan; plan **cleared to implement**. Structurally sound (stage decomposition, hard-stop checkpoints, TDD discipline, no backward-compat shims, no speculative surface). All P1 + P2 items integrated.

**Round 1 — P1 resolution (prior session):**
1. **Item A migration sweep** — explicit migration step added: 3 production sites (`base_exceptions.py:135`, `base_exceptions.py:166`, `cogt/exceptions.py:88`) + mixed strategy for test fixtures (real values where serialization is under test, conftest helper elsewhere).
2. **Item C RFC 7807 mapping** — `to_problem_document` maps `type_uri → type` and `title → title`, dropping both from extension members. Single-`title`-key + `type == type_uri` contract test added.

**Round 1 — P2 resolution (prior session):**
- `_DEFAULT_ERRORS_BASE_URI` fallback rejected; default lives in `pipelex/pipelex.toml`.
- Curated `_declared_title` for `PipelexError` / `PipelexUnexpectedError` / `SecurityError` added; wide sweep in scope for Item A's PR.
- `pascal_case_to_kebab` tests for numerics + trailing acronyms added (including `"OAuth2" → "o-auth2"` pin).
- `ErrorReport.from_dict` missing-required-fields → `ValidationError` test added.
- Receiver-rehydration test added to Item C.

**Round 2 — P1 finding (this session):**
1. **`pipelex/pipeline/exceptions.py:44` uses `dataclasses.replace(report, ...)` — breaks under Item D-2's `BaseModel` conversion.** `dataclasses.replace()` is stdlib-dataclass-only; BaseModel uses `model_copy(update=...)`. Folded into Item D-2's migration sweep: drop the `from dataclasses import replace` import and rewrite the call. Regression test added (`PipelineExecutionError.to_error_report()` floor behavior).

**Round 2 — P2 finding (this session):**
- **`WorkflowExecutionError` wrapper-loses carve-out documented in "Decisions locked in"** above. Prevents future implementer from "fixing" the asymmetry by adding `_enrich_error_report_from_cause(report)` to the override during Item A implementation, which would break the Temporal boundary that this exception exists to bridge.

**Round 2 — Informational (not blocking):**
- Plan's "~267 `PipelexError` subclasses" count is overestimated. Actual: ~77 direct subclasses (`grep "^class .*(.*PipelexError"`); ~257 total `Error`-named classes, but many are stdlib or pydantic-derived. The "wide sweep" is a smaller job than the plan suggests, but the strategy ("focused pass through every leaf class whose auto-derived title reads badly") still applies — just less work than estimated.

**Round 2 — Verifications performed:**
- All file:line references in the plan verified against the codebase (`base_exceptions.py:135`, `:166`, `cogt/exceptions.py:88`, `workflow_caller.py:128`, `:240`, `:292`).
- `pascal_case_to_sentence` confirmed present at `pipelex/tools/misc/string_utils.py:121` — `pascal_case_to_kebab` adjacent placement is sound.
- `JobMetadata` confirmed `BaseModel` already — Item B's `request_id` field is a clean addition.
- No existing `errors_config` / `error_base_uri` in the codebase — Item A introduces it without conflict.

**Round 3 — P1 finding (this session):**
1. **`tests/unit/pipelex/test_base_exceptions.py::test_error_report_constructable_without_cogt_exceptions_loaded` will break under Item A.** The subprocess that test runs does TWO things that fail after Item A: (a) constructs `ErrorReport(error_type='X', message='m')` which becomes a `ValidationError` (missing required `title`/`type_uri`), and (b) calls `PipelexConfigError('boom').to_error_report()` which calls `type_uri()` → `get_config()` → `RuntimeError` because the subprocess never bootstraps Pipelex. Per the locked-in "no fallback constant" decision, the `get_config()` failure is by design — but the existing cold-import regression test needs an explicit migration step. Folded into Item A's migration sweep: the test drops the `to_error_report()` line and constructs `ErrorReport` directly with explicit `title`/`type_uri`. A separate non-subprocess test asserts `PipelexConfigError.to_error_report()` with config loaded (the normal pytest fixture chain handles bootstrapping).

**Round 3 — P2 findings (this session):**
1. **User-visible behavior change at `workflow_caller.py:131-134` is not pinned by any test.** After Item D-1 drops the `if error_report is not None` branch, the unrecoverable path's `WorkflowExecutionError.message` changes from the Pipelex-framed `"Failed to execute workflow X"` to the synthesized `message_from_exc(exc)` (typically Temporal's own message or `repr(exc)`). This is intentional and more diagnostic, but no end-to-end test pins the new contract. Folded into Item D-1: a new end-to-end test in `test_workflow_caller_error_recovery.py` asserts a non-Pipelex `WorkflowFailureError` surfaces with the synthesized message, NOT the legacy fallback string, and that `error_report.error_type == "UnrecoverableWorkflowFailureError"`.
2. **Existing `test_workflow_execution_error.py` G7-shaped tests look like dead code after D-1 but aren't.** `WorkflowExecutionError(msg)` without `error_report=...` is still reachable via `start_workflow` (catches only `WorkflowAlreadyStartedError` / `RPCError`) and the `WorkflowAlreadyStartedError` / `RPCError` branches of `execute_workflow`. Folded into Item D-1's "Note on no-longer-reached paths" — a future implementer must not remove those tests as "dead" during D-1.

**Round 3 — Verifications performed:**
- Confirmed `temporal_pipe_router.py:89-91` (in-workflow child dispatch) re-wraps `ChildWorkflowError` as `WorkflowExecutionError(msg) from exc` without explicit report recovery. Initially flagged as a 4th missing call site, but **invalidated** by `test_recovers_report_past_report_less_wrapper_application_error` (test_recover_error_report.py:70-79) — the recover walk passes through report-less wrapper `ApplicationError`s, so the inner report still surfaces at the submitter boundary regardless of the in-workflow re-wrap. No plan change needed.
- Verified `BaseModelPayloadConverter.from_payload` (temporal_data_converter.py:147-148) already handles `Optional[BaseModel]` via `_unwrap_optional_base_model` — Item D-2's `error_report: ErrorReport | None` arg is a clean addition with no converter surgery.
- Verified `pipeline/exceptions.py:1, :44` uses `dataclasses.replace` as the Round-2 finding flagged. Item D-2 migration sweep covers this.
