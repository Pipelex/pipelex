# TODOS — pipelex changes for the pipelex-api error-handling refactor

This worktree (`feature/API-readiness`) carries the **pipelex-side** companion work for the `pipelex-api` error-handling design. The original per-item spec is in [`wip/error-handling/changes-for-api-early-draft.md`](wip/error-handling/changes-for-api-early-draft.md); the deviations we are taking from that spec — and *why* — are documented in [`wip/error-handling/api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md). The cross-repo consumer (the API) lives in the side-by-side worktree [`../pipelex-api/wip/error-handling/`](../../pipelex-api/wip/error-handling/).

This file is the **execution plan** — what to land, in what order, with hard-stop checkpoints. The 9 items of the original spec consolidate to 6 here. See [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) for the full rationale.

---

## Decisions locked in

The plan reflects these decisions; no further re-litigation in the items below.

- **`ErrorReport` becomes a `BaseModel`** (`model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`). We drop the `@pydantic.dataclasses.dataclass` form. The existing Temporal data converter already handles `BaseModel` round-trips — no kajson surgery needed. (Was Item D-2's open question.)
- **`ErrorReport.title` and `type_uri` are required `str`**, not `str | None`. Every fresh report carries them. A payload missing them fails `from_dict`, which `recover_error_report` synthesizes as `UnrecoverableWorkflowFailureError` (Item D-1) — the correct behavior under "no backward-compat shims."
- **`request_id` propagates via `JobMetadata` only.** No ContextVar layer for propagation — Temporal serializes the activity arg; only fields on `JobMetadata` cross the worker boundary. Activity-side log binding reads `arg.<path>.job_metadata.request_id` directly from the arg.
- **`UnrecoverableWorkflowFailureError` lives in `pipelex/temporal/exceptions.py`**, not `base_exceptions.py`. It's a Temporal-flow-specific synthesis concept.
- **`errors_config` lives under `Pipelex` config**: `get_config().pipelex.errors_config.base_uri`. Consistent with `pipe_run_config`, `pipeline_execution_config`, etc.
- **`error_category` is kept in STRICT mode** alongside the other stable identifiers. Revisit only if a deployment surfaces it as a data-leak.
- **Stage 3 acceptance covers the full `WfPipeRun` chain**, not just `WfPipeRouter`. The existing test bypasses `WfPipeRun`; the new test exercises the outer wrap so the inner child's report survives.

---

## Approach

- **Stages map to API-plan dependencies, not effort.** Land in stage order so the API team can start consuming primitives as early as possible.
- **TDD red-green per item.** Add the failing test against the desired surface first, then implement until it passes. Pre-existing tests under `tests/unit/pipelex/test_base_exceptions.py`, `tests/unit/pipelex/test_error_report_from_dict.py`, `tests/unit/pipelex/pipe_run/test_delivery_executor.py`, `tests/unit/pipelex/temporal/test_recover_error_report.py`, and `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` are the natural homes for the new cases.
- **After every item:** run `make agent-check` and `make agent-test`. Both must pass before checking off the item.
- **No backward-compatibility shims, no curate-a-subset hedges, no "consumer fallback for missing data" patterns.** Pipelex owns the defaults so every consumer gets the same behavior automatically.

---

## Stage 1 — Foundations *(unblocks `pipelex-api` Phase 0)*

### [ ] Item A — `PipelexError.title()` + `type_uri()` with auto-derive defaults *(merges spec items 1+2)*

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
- **Curated overrides shipped with this item** (concrete list, not "to be discovered later"):
    - `CogtError._declared_title = "AI inference failed"`
    - `EnvVarNotFoundError._declared_title = "Environment variable not set"`
    - Plus any other auto-derive that reads badly — survey at implementation time and curate in this PR. Do NOT defer to a follow-up.
- **Tests** (`tests/unit/pipelex/test_base_exceptions.py`):
    - Auto-derive: `class FooBarError(PipelexError): pass` → `FooBarError.title() == "Foo bar"`, `type_uri() == "https://pipelex.dev/errors/foo-bar"`.
    - Override wins: `class X(PipelexError): _declared_title = "Custom"` → `X.title() == "Custom"`.
    - Round-trip: `ErrorReport.model_validate(report.model_dump()).title == report.title` and same for `type_uri`.
    - **Uniqueness guard:** a test that walks `PipelexError.__subclasses__()` recursively (forcing imports of the relevant `*/exceptions.py` modules first) and asserts every class's `type_uri()` is unique. Catches future class-name collisions at CI time, not docs-build time.
    - `pascal_case_to_kebab`: `"FooBarBaz"` → `"foo-bar-baz"`; `"APIError"` → `"api-error"`; `"EnvVarNotFound"` → `"env-var-not-found"`.
- **Acceptance:** consumers never humanize or kebab-case a class name themselves. The API consumes `report.title` / `report.type_uri` directly.

### [ ] Item B — First-class `request_id` on `JobMetadata` *(spec item 3)*

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

### [ ] Item C — Parameterized `to_dict(disclosure_mode=)` + `to_problem_document(...)` *(merges spec items 4+6)*

- **File:** `pipelex/base_exceptions.py`
- **Surface:**
    ```python
    class DisclosureMode(StrEnum):
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
- **`from_dict` / `to_dict` semantics.** `to_dict(VERBOSE)` is the inverse of `from_dict`; the round-trip is preserved. `to_dict(STRICT)` is a **lossy** projection — `from_dict(to_dict(report, STRICT))` does not reconstruct the original. Document this on the docstring. Webhook payloads use VERBOSE so receivers can rehydrate (`ErrorReport.from_dict(payload["error"])`); HTTP responses use whatever disclosure the deployment configured.
- **Strict redaction rule:**
    - `INPUT`-domain reports → returned unchanged (the caller's own input; reflecting it back is fine).
    - `CONFIG` / `RUNTIME` reports → `message` replaced with `"An internal error occurred."`; `provider`, `model`, `provider_metadata`, `user_action` dropped.
    - **Kept in all modes** (stable identifiers, RFC 7807-compatible): `error_type`, `error_domain`, `error_category`, `retryable`, `title`, `type_uri`.
- **`to_problem_document`** builds the RFC 7807 envelope (`type`, `title`, `status`, `detail`, `instance`) from the report's fields; pipelex `ErrorReport` fields ride as extension members. Honors `disclosure_mode` by calling `to_dict(disclosure_mode)` internally. `request_id` lands as the `request_id` extension member. Returns a plain dict — pipelex stays HTTP-agnostic, no FastAPI/Starlette import.
- **Tests:**
    - Parametrize across the three domains × two disclosure modes (six base cases). Assert INPUT passthrough; CONFIG/RUNTIME redaction-with-stable-identifiers-kept.
    - Parametrize `retryable: True | False | None` × `disclosure_mode: VERBOSE | STRICT`. Assert `retryable` survives both modes for all three values.
    - **INPUT-strict pin test:** an INPUT report whose `message` contains a path like `/Users/alice/secret.mthds` is returned **unchanged** in STRICT mode. Pin the documented contract.
    - RFC 7807 shape: `to_problem_document(instance="urn:p:123", request_id="r-1")` returns a dict with `type`, `title`, `status`, `detail`, `instance="urn:p:123"`, and a `request_id="r-1"` extension member.
    - Verbose round-trip: `from_dict(report.to_dict(VERBOSE))` equals `report`.
    - Strict non-round-trip: `from_dict(report.to_dict(STRICT))` for a RUNTIME report has `message == "An internal error occurred."` and `provider is None`.
- **Acceptance:** the API consumes both methods directly. The redaction rule and the envelope shape live exactly once in pipelex; no consumer duplicates them.

### [ ] Item D-1 — Make `recover_error_report` total

- **Files:**
    - `pipelex/temporal/exceptions.py` — new subclass `UnrecoverableWorkflowFailureError(TemporalFlowError)` with `error_domain = ErrorDomain.RUNTIME` and `_declared_title = "Workflow failed without recoverable error details"`. Lives next to `TemporalFlowError`, `WorkflowExecutionError`, etc. (Reason: Temporal-flow-specific synthesis concept; locking it into the Temporal exceptions module keeps the base hierarchy clean.)
    - `pipelex/temporal/tprl/temporal_error.py` — `recover_error_report` signature becomes `def recover_error_report(exc: BaseException) -> ErrorReport`. When no embedded report is found or `from_dict` fails on version skew, synthesizes `UnrecoverableWorkflowFailureError(message_from_exc(exc)).to_error_report()`. `message_from_exc` extracts the most informative message available: the outer Temporal failure's message if non-empty, else `repr(exc)`.
    - `pipelex/temporal/tprl/workflow_caller.py` — call sites at `:128`, `:240`, `:292`: drop the `if error_report is not None` branches; the return is always usable.
- **Tests** (`tests/unit/pipelex/temporal/test_recover_error_report.py`):
    - Existing case `test_g3_malformed_details_recovers_nothing` becomes `test_g3_malformed_details_synthesizes_unrecoverable` and asserts the synthesized report has `error_type == "UnrecoverableWorkflowFailureError"`, `error_domain == "runtime"`, `retryable is None`, message contains the original exception message.
    - Existing case `test_g4_application_error_without_report_details_recovers_nothing` becomes `test_g4_application_error_without_report_details_synthesizes_unrecoverable` with the same assertions.
    - Existing case `test_no_application_error_in_chain_recovers_nothing` becomes `test_no_application_error_in_chain_synthesizes_unrecoverable`.
    - Existing positive cases continue to assert recovery of the packed report unchanged.
- **Acceptance:** callers never see `None` from this function. The "hand-author a fallback report" pattern the original spec proposed (see [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §D) is eliminated — there is exactly one place that constructs the unrecoverable report.

**Checkpoint 2 — End of Stage 2** ⬇ See [Checkpoint 2 brief](#checkpoint-2--end-of-stage-2) below.

---

## Stage 3 — Async error pipe *(unblocks `pipelex-api` Phase 4 — most important item)*

### [ ] Item D-2 — Thread `ErrorReport` to the webhook

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

**Checkpoint 4 — End of Stage 4** ⬇ See [Checkpoint 4 brief](#checkpoint-4--end-of-stage-4) below.

---

## Stage 5 — Security tightening *(cross-repo coordination needed)*

### [ ] Item F — `X-Completion-Signature` covers the full webhook payload *(spec item 9)*

- **Files:**
    - `pipelex/system/configuration/configs.py` + `pipelex/pipelex.toml` — new `webhook_signing_secret: str | None` on `PipelineExecutionConfig`. Default `None` (development convenience); production deployments set it.
    - `pipelex/pipe_run/delivery_executor.py:_notify_webhook` — compute `HMAC-SHA256(secret, request_body_bytes)`, header `X-Completion-Signature: sha256=<hex>`. When the secret is `None` and a webhook is configured, raise `PipelexConfigError("Webhook signing secret not configured; set pipelex.pipeline_execution_config.webhook_signing_secret or PIPELEX_WEBHOOK_SIGNING_SECRET")`. Loud failure, not silent unsigned send. The secret resolves from config OR the `PIPELEX_WEBHOOK_SIGNING_SECRET` environment variable (config takes precedence) for ops convenience.
    - **Cross-repo:** `pipelex-api/api/routes/pipelex/pipeline.py:_completion_signature` updated to verify the same way (take body bytes, recompute, constant-time compare via `hmac.compare_digest`). Land both PRs in coordinated lockstep.
- **Tests** (`tests/unit/pipelex/pipe_run/test_delivery_executor.py`):
    - Signature is deterministic for fixed (secret, body) pairs.
    - Signature matches what `hmac.new(secret, body, sha256).hexdigest()` produces (compare to the receiver-side computation).
    - Flipping a single byte in the body produces a different signature.
    - Missing-secret-with-webhook-configured raises `PipelexConfigError` with the configuration hint in the message.
    - Webhook with no recipients (empty `delivery_assignment.webhooks`) succeeds without requiring the secret.
- **Acceptance:** rewriting `status`, `result_url`, or `error` in transit causes signature verification to fail on the receiver. Cross-repo PRs both green.

**Final checkpoint — End of Stage 5** ⬇ See [Final checkpoint brief](#final-checkpoint--end-of-stage-5) below.

---

## What we dropped from the original spec

| Spec item | Why dropped |
|---|---|
| Item 8 — `query_pipeline_state(...)` | Speculative future work; no current consumer needs it. Repo CLAUDE.md: *"Don't design for hypothetical future requirements."* Will be revisited when the first consumer materializes with concrete requirements. |

See [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) for the full reasoning on this and the consolidations above.

---

## Tracking

| ID | Item | Stage | Status |
|---|---|---|---|
| A | `PipelexError.title()` + `type_uri()` with auto-derive *(spec 1+2)* | 1 | [ ] |
| B | `request_id` on `JobMetadata` *(spec 3)* | 1 | [ ] |
| C | `to_dict(disclosure_mode=)` + `to_problem_document(...)` *(spec 4+6)* | 2 | [ ] |
| D-1 | Total `recover_error_report` | 2 | [ ] |
| D-2 | `ErrorReport` → `BaseModel`; thread to webhook; full `WfPipeRun` chain test *(spec 5)* | 3 | [ ] |
| E | Per-class doc pages *(spec 7)* | 4 | [ ] |
| F | Full-payload webhook signature *(spec 9)* | 5 | [ ] |

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
- Curated `_declared_title` overrides landed: _TBD_
- Files touched: _TBD_
- Surprises / deviations (record in `api-companion-revisions.md`): _TBD_

**Cold-start for Checkpoint 2:**
- Re-read items C + D-1 here, and [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §C + §D.
- Skim `pipelex/temporal/tprl/temporal_error.py:recover_error_report` and its three call sites in `workflow_caller.py`.
- Run `git log --oneline -20` and `make agent-test` to confirm starting clean.

---

### Checkpoint 2 — End of Stage 2

**What should be true:**
- `DisclosureMode` enum in `pipelex/base_exceptions.py`.
- `ErrorReport.to_dict(disclosure_mode=...)` and `ErrorReport.to_problem_document(...)` exist and behave per the redaction rule (stable identifiers kept, message redacted for CONFIG/RUNTIME, INPUT passthrough).
- Verbose round-trip preserved; strict round-trip explicitly documented as lossy.
- `recover_error_report` is total: `BaseException -> ErrorReport`. `UnrecoverableWorkflowFailureError` lives in `pipelex/temporal/exceptions.py`. All three call sites in `workflow_caller.py` are simplified.
- `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Files touched: _TBD_

**Cold-start for Checkpoint 3:**
- Re-read Item D-2 + [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §D. This is the load-bearing stage.
- The `BaseModel` conversion is the gate — land the round-trip test before the activity arg change.
- Confirm the new `WfPipeRun` end-to-end test is in scope, not deferred. The existing test bypasses `WfPipeRun`; the new test is the safety net for the outer Temporal wrap.

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
- Files touched: _TBD_
- Confirmation that the workflow's "preserve `execution_error` for failure attribution" reordering still holds (current `wf_pipe_run.py:132` comment): _TBD_
- **Notify the API team** that Stages 1–3 are landed and their Phases 0/1/4 are unblocked. Update [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) "current state" section.

**Cold-start for Checkpoint 4:**
- Stage 4 is docs polish. Re-read Item E.
- Read `docs/under-the-hood/error-model.md` to understand the docs site layout.
- Confirm docs build cleanly locally before starting.

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

**Cold-start for the final checkpoint:**
- Stage 5 is cross-repo. Confirm with the API team before starting — they own the receiver-side change.
- Read `pipelex/pipe_run/delivery_executor.py:_notify_webhook` to confirm the current signature shape.

---

### Final checkpoint — End of Stage 5

**What should be true:**
- HMAC over body bytes; `X-Completion-Signature: sha256=<hex>`.
- pipelex-api signature verification matches; cross-repo PRs both green.
- Tamper-detection tests cover single-byte body changes; missing-secret-with-webhook-configured raises `PipelexConfigError`.
- `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Cross-repo PR link: _TBD_
- Secret source / rotation story confirmed: _TBD_
- Files touched: _TBD_

**Post-completion:** mark [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) "current state" section as fully landed; replace this `TODOS.md` with a short pointer to the merged PRs.

---

## Where to look when starting cold

1. This `TODOS.md` — find the first unchecked item and its checkpoint context. **Read the "Decisions locked in" section at the top first** — the items below assume them.
2. [`wip/error-handling/api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) — what we are actually building vs. what the original spec proposed, with rationale per item. **The pipelex-api agent reads this to know what to expect.**
3. [`wip/error-handling/changes-for-api-early-draft.md`](wip/error-handling/changes-for-api-early-draft.md) — the original spec, kept for context but superseded by the revisions doc.
4. [`wip/error-handling/README.md`](wip/error-handling/README.md) — the broader error-handling landscape.
5. The most recent checkpoint's "Fill in at checkpoint time" block — running notes from the previous session.
6. `git log --oneline -20` to see the most recent landings.

The cross-repo counterpart lives in [`../pipelex-api/wip/error-handling/`](../../pipelex-api/wip/error-handling/) — open it side-by-side when reasoning about items D-2 and F.
