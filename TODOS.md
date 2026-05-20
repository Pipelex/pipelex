# TODOS — pipelex changes for the pipelex-api error-handling refactor

This worktree (`feature/API-readiness`) carries the **pipelex-side** companion work for the `pipelex-api` error-handling design. The original per-item spec is in [`wip/error-handling/pipelex-changes.md`](wip/error-handling/pipelex-changes.md); the deviations we are taking from that spec — and *why* — are documented in [`wip/error-handling/api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md). The cross-repo consumer (the API) lives in the side-by-side worktree [`../pipelex-api/wip/error-handling/`](../../pipelex-api/wip/error-handling/).

This file is the **execution plan** — what to land, in what order, with hard-stop checkpoints. The 9 items of the original spec consolidate to 6 here. See [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) for the full rationale.

---

## Approach

- **Stages map to API-plan dependencies, not effort.** Land in stage order so the API team can start consuming primitives as early as possible.
- **TDD red-green per item.** Add the failing test against the desired surface first, then implement until it passes. Pre-existing tests under `tests/unit/pipelex/test_base_exceptions.py`, `tests/unit/pipelex/test_error_report_from_dict.py`, `tests/unit/pipelex/pipe_run/test_delivery_executor.py`, and `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` are the natural homes for the new cases.
- **After every item:** run `make agent-check` and `make agent-test`. Both must pass before checking off the item.
- **No backward-compatibility shims, no curate-a-subset hedges, no "consumer fallback for missing data" patterns.** Pipelex owns the defaults so every consumer gets the same behavior automatically.

---

## Stage 1 — Foundations *(unblocks `pipelex-api` Phase 0)*

### [ ] Item A — `PipelexError.title()` + `type_uri()` with auto-derive defaults *(merges spec items 1+2)*

- **File:** `pipelex/base_exceptions.py` (+ a tiny helper module if humanize/kebab-case lives elsewhere).
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
            return cls._declared_type_uri or f"{_base_error_uri()}/{_kebab(cls.__name__)}"
    ```
    `ErrorReport` gains `title: str | None = None` and `type_uri: str | None = None` (round-trip through `to_dict` / `from_dict`). `PipelexError.to_error_report()` populates both from `type(self).title()` / `type(self).type_uri()` — never `None` on a real report.
- **Base URI:** read from `get_config().errors.base_uri` (new config key; default `"https://pipelex.dev/errors"`).
- **Curation:** override `_declared_title` / `_declared_type_uri` only when the auto-derive is bad copy or the URI needs to point somewhere other than the default anchor. **Do not curate "a subset" — every class works out of the box.**
- **Tests:**
    - Auto-derive: `EnvVarNotFoundError.title() == "Environment variable not set"` *(if curated)* or `== "Env var not found"` *(if not)*; URI is `https://pipelex.dev/errors/env-var-not-found`.
    - Round-trip: `ErrorReport.from_dict(report.to_dict())` preserves both fields.
- **Acceptance:** consumers never humanize or kebab-case a class name themselves. The API consumes `report.title` / `report.type_uri` directly.

### [ ] Item B — First-class `request_id` on `JobMetadata` *(spec item 3)*

- **Files:**
    - `pipelex/pipeline/job_metadata.py` — add `request_id: str | None = None` next to `pipeline_run_id` / `user_id` / `session_id`.
    - `pipelex/pipeline/pipeline_run_setup.py` — `pipeline_run_setup(...)` accepts a `request_id: str | None = None` kwarg and threads it into `JobMetadata`.
    - `pipelex/temporal/log_temporal.py` (or sibling) — bind `request_id` into a `ContextVar` on activity entry so every log record carries it. Use the same pattern as `session_id` propagation (`stamp_submitter_session_id` in `pipelex/temporal/tprl/observability.py`).
- **Tests:**
    - `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` — extend a case to dispatch with a known `request_id`, assert it appears in activity log records on success and failure paths.
- **Acceptance:** a `request_id` passed to `pipeline_run_setup(...)` shows up in worker logs emitted from inside the workflow with no consumer-side workaround. The current `webhook.payload["request_id"]` piggyback in the API becomes obsolete.

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

    class ErrorReport:
        def to_dict(self, disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE) -> dict[str, Any]: ...
        def to_problem_document(
            self,
            *,
            instance: str | None = None,
            request_id: str | None = None,
            disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE,
        ) -> dict[str, Any]: ...
    ```
- **Strict redaction rule** (revised from the original spec, see [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §C):
    - `INPUT`-domain reports → returned unchanged.
    - `CONFIG` / `RUNTIME` reports → `message` replaced with `"An internal error occurred."`; `provider`, `model`, `provider_metadata`, `user_action` dropped.
    - **Kept in all modes** (stable type identifiers, RFC 7807-compatible): `error_type`, `error_domain`, `error_category`, `retryable`, `title`, `type_uri`.
- **`to_problem_document`** builds the RFC 7807 envelope (`type`, `title`, `status`, `detail`, `instance`) from the report's fields; pipelex `ErrorReport` fields ride as extension members. Honors `disclosure_mode` by calling `to_dict(disclosure_mode)` internally. Returns a plain dict — pipelex stays HTTP-agnostic, no FastAPI/Starlette import.
- **Tests:**
    - Parametrize across the three domains × two disclosure modes; verify INPUT passthrough, CONFIG/RUNTIME redaction-with-identifiers-kept, RFC 7807 shape.
- **Acceptance:** the API consumes both methods directly. The redaction rule and the envelope shape live exactly once in pipelex; no consumer duplicates them.

### [ ] Item D-1 — Make `recover_error_report` total *(prep for spec item 5)*

- **Files:**
    - `pipelex/base_exceptions.py` (or `pipelex/temporal/exceptions.py`) — new subclass `UnrecoverableWorkflowFailureError(PipelexError)` with `error_domain = ErrorDomain.RUNTIME` and `_declared_title = "Workflow failed without recoverable error details"`.
    - `pipelex/temporal/tprl/temporal_error.py` — `recover_error_report` no longer returns `Optional`; signature becomes `def recover_error_report(exc: BaseException) -> ErrorReport`. When no embedded report is found or `from_dict` fails on version skew, it synthesizes `UnrecoverableWorkflowFailureError(...).to_error_report()` (which carries `retryable=None`, real `error_type`, real `error_domain`, the original exception message as the report message).
    - Update every call site (`workflow_caller.py:128, 240, 292`) — drop the `if error_report is not None` branches; the return is always usable.
- **Tests:**
    - `tests/unit/pipelex/temporal/test_recover_error_report.py` — extend with the "no details" and "malformed details" cases; assert the synthesized report has the right `error_type` / `error_domain` / `retryable`.
- **Acceptance:** callers never see `None` from this function. The "hand-author a fallback report" pattern the original spec proposed (see [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §D) is eliminated — there is exactly one place that constructs the unrecoverable report.

**Checkpoint 2 — End of Stage 2** ⬇ See [Checkpoint 2 brief](#checkpoint-2--end-of-stage-2) below.

---

## Stage 3 — Async error pipe *(unblocks `pipelex-api` Phase 4 — most important item)*

### [ ] Item D-2 — Thread `ErrorReport` to the webhook *(completes spec item 5)*

- **Prereq verification:** confirm the pipelex Temporal data converter (`pipelex/temporal/temporal_data_converter.py`) handles `ErrorReport` correctly. Today it only handles `BaseModel` and `list[BaseModel]`; `ErrorReport` is a frozen Pydantic dataclass and **will not round-trip as-is**. Two paths, in order of preference:
    1. **Extend the data converter (and `kajson` if needed)** to handle Pydantic dataclasses generically. This benefits any future dataclass on a workflow arg. Per the user's stated preference, this is the path to take.
    2. **Fallback:** convert `ErrorReport` from `@dataclass(frozen=True)` to a `BaseModel` with `model_config = ConfigDict(frozen=True)`. Smaller diff but loses the dataclass ergonomics and changes the existing `to_dict`/`from_dict` implementation.
    - **Whichever path:** add a round-trip test (`tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py` is the existing home) before wiring `ErrorReport` into the activity arg.
- **Files:**
    - `pipelex/pipe_run/delivery_executor.py` — `execute(...)` and `_notify_webhook(...)` accept `error_report: ErrorReport | None = None`. When `status == FAILED` and `error_report is not None`, the webhook payload includes `error = error_report.to_dict()`. (Default verbose disclosure; the API can choose strict mode at its own surface.)
    - `pipelex/temporal/tprl_pipe/act_deliver.py` — `DeliveryActivityArg` gains `error_report: ErrorReport | None = None` (no `_dict` shim; the data converter handles it after the prereq).
    - `pipelex/temporal/tprl_pipe/wf_pipe_run.py` — on the `ChildWorkflowError` catch, call `error_report = recover_error_report(exc.cause)` (total — always a value, see item D-1). Pass it into `DeliveryActivityArg`.
- **Tests:**
    - `tests/unit/pipelex/pipe_run/test_delivery_executor.py` — webhook payload includes `error` on `FAILED` + non-`None`; absent on `COMPLETED` or `None`. Round-trips a realistic `ErrorReport` with `provider_metadata` populated (no `body` — already excluded upstream).
    - `tests/integration/pipelex/temporal/test_workflow_error_report_full_chain.py` — extend to cover a worker-side `CogtError` failure reaching the webhook with classification intact (`error_type`, `error_category`, `retryable`, `user_action`, `title`, `type_uri`).
- **Acceptance:** a Temporal-side pipe failure reaches the webhook with the same classification a sync caller would see locally. No silent loss of fields across activity → workflow → delivery.

**Checkpoint 3 — End of Stage 3 (largest unlock; recommended stopping point if context is tight)** ⬇ See [Checkpoint 3 brief](#checkpoint-3--end-of-stage-3) below.

---

## Stage 4 — DX polish *(pairs with `pipelex-api` Phase 5)*

### [ ] Item E — Per-class `type` URI doc pages *(spec item 7)*

- **Files:** `docs/` (mkdocs).
- **Generator:** a small mkdocs hook (or `pipelex-dev` CLI subcommand — choose at implementation time based on what fits best with the existing docs build pipeline) that walks the `PipelexError` hierarchy and emits one page per class, anchored at the URI returned by `cls.type_uri()`.
- **Page content:** class name, `cls.title()`, domain, typical `user_action`, link to parent class doc, back-link to the schema page. Authors override per-class content where it adds value.
- **Tests:** none (docs build verifies generation; reviewers eyeball a few pages).
- **Acceptance:** clicking a `type` URI from a real error response lands on a populated page. Adding a new `PipelexError` subclass produces a new doc page automatically on next build.

**Checkpoint 4 — End of Stage 4** ⬇ See [Checkpoint 4 brief](#checkpoint-4--end-of-stage-4) below.

---

## Stage 5 — Security tightening *(cross-repo coordination needed)*

### [ ] Item F — `X-Completion-Signature` covers the full webhook payload *(spec item 9)*

- **Files:**
    - `pipelex/pipe_run/delivery_executor.py:_notify_webhook` — compute `HMAC-SHA256(secret, request_body_bytes)`, header `X-Completion-Signature: sha256=<hex>`. Secret source: `get_config().pipeline_execution_config.webhook_signing_secret` (new config key; falls back to environment variable for ops convenience).
    - **Cross-repo:** `pipelex-api/api/routes/pipelex/pipeline.py:_completion_signature` updated to verify the same way (take body bytes, recompute, constant-time compare). Land both PRs in coordinated lockstep.
- **Tests:**
    - `tests/unit/pipelex/pipe_run/test_delivery_executor.py` — signature is deterministic; matches what the receiver computes; flips when the body changes by a single byte; missing-secret path raises a clear `PipelexConfigError`.
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
| D-1 | Total `recover_error_report` *(prep for spec 5)* | 2 | [ ] |
| D-2 | Thread `ErrorReport` to webhook *(completes spec 5)* | 3 | [ ] |
| E | Per-class doc pages *(spec 7)* | 4 | [ ] |
| F | Full-payload webhook signature *(spec 9)* | 5 | [ ] |

---

## Checkpoints

Each checkpoint **must** end with: (a) all checkboxes in that stage checked, (b) `make agent-check` clean, (c) `make agent-test` clean, (d) this section updated with concrete file:line references for what landed, (e) any deviations from the plan recorded in [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md), (f) cold-start instructions confirmed for the next session.

Checkpoints are **hard stops**. Do not pick up the next stage in the same session — context will have grown and the next session is cheaper to start fresh.

### Checkpoint 1 — End of Stage 1

**What should be true:**
- `PipelexError` has `_declared_title` / `_declared_type_uri` ClassVars + `title()` / `type_uri()` classmethods with auto-derive defaults.
- `ErrorReport` carries `title` and `type_uri` fields; round-trips through `to_dict` / `from_dict`.
- `get_config().errors.base_uri` exists with default `"https://pipelex.dev/errors"`.
- `JobMetadata.request_id` exists; `pipeline_run_setup(...)` accepts it; activity-side logs carry it via ContextVar.
- All new tests exist and pass; `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Curated overrides landed (if any beyond defaults): _TBD_
- Humanize/kebab helper location: _TBD_
- ContextVar mechanism for `request_id`: _TBD_
- Surprises / deviations (record in `api-companion-revisions.md`): _TBD_
- Files touched: _TBD_

**Cold-start for Checkpoint 2:**
- Re-read items C + D-1 here, and [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §C + §D.
- Skim `pipelex/temporal/tprl/temporal_error.py:recover_error_report` and its three call sites in `workflow_caller.py`.
- Run `git log --oneline -20` and `make agent-test` to confirm starting clean.

---

### Checkpoint 2 — End of Stage 2

**What should be true:**
- `DisclosureMode` enum in `pipelex/base_exceptions.py`.
- `ErrorReport.to_dict(disclosure_mode=...)` and `ErrorReport.to_problem_document(...)` exist and behave per the revised redaction rule (stable identifiers kept).
- `recover_error_report` is total: `BaseException -> ErrorReport`. `UnrecoverableWorkflowFailureError` exists. All three call sites in `workflow_caller.py` are simplified.
- `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Exact strict-mode placeholder string used: _TBD_
- `UnrecoverableWorkflowFailureError` placement (`base_exceptions.py` vs `temporal/exceptions.py`): _TBD_
- Files touched: _TBD_

**Cold-start for Checkpoint 3:**
- This is the load-bearing stage. Re-read item D-2 + [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) §D (data-converter section).
- Skim `pipelex/temporal/temporal_data_converter.py` and `pipelex/tools/serde/kajson` — the data-converter / kajson extension is the prerequisite work.
- Run `make agent-test` to confirm clean.

---

### Checkpoint 3 — End of Stage 3

**Biggest unlock; strong stopping point.** After this, the API team can build Phase 4 against a lossless contract.

**What should be true:**
- Temporal data converter handles `ErrorReport` (Pydantic dataclass) round-trips, via converter/kajson extension. Round-trip test passes.
- `DeliveryActivityArg.error_report: ErrorReport | None` (no `_dict` shim).
- `DeliveryExecutor.execute(error_report=...)` and `_notify_webhook(error_report=...)` write `payload["error"] = error_report.to_dict()` on `FAILED`.
- `wf_pipe_run` recovers the report via total `recover_error_report(exc.cause)` and threads it through.
- Full-chain integration test demonstrates classification (`error_type`, `error_category`, `retryable`, `user_action`, `title`, `type_uri`) surviving from a worker-side `CogtError` into the webhook payload.
- `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Path taken for dataclass support (converter/kajson extension vs `BaseModel` conversion): _TBD_
- Whether the workflow's "preserve `execution_error` for failure attribution" reordering still holds (current `wf_pipe_run.py:132` comment): _TBD_
- Files touched: _TBD_
- **Notify the API team** that Stages 1–3 are landed and their Phases 0/1/4 are unblocked. Update [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) "current state" section.

**Cold-start for Checkpoint 4:**
- Stage 4 is docs polish. Re-read item E.
- Read `docs/under-the-hood/error-model.md` to understand the docs site layout.
- Confirm docs build cleanly locally before starting.

---

### Checkpoint 4 — End of Stage 4

**What should be true:**
- mkdocs build emits per-class type-URI stub pages from the `PipelexError` hierarchy automatically.
- A few high-traffic classes have authored overrides; the rest use the generated default and look sensible.
- Docs build clean; `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Generator location + invocation: _TBD_
- Per-class page location (e.g. `docs/errors/<kebab>.md`): _TBD_
- Files touched: _TBD_

**Cold-start for the final checkpoint:**
- Stage 5 is cross-repo. Confirm with the API team before starting — they own the receiver-side change.
- Read `pipelex/pipe_run/delivery_executor.py:_notify_webhook` to confirm the current signature shape.

---

### Final checkpoint — End of Stage 5

**What should be true:**
- HMAC over body bytes; `X-Completion-Signature: sha256=<hex>`.
- pipelex-api signature verification matches; cross-repo PRs both green.
- Tamper-detection tests cover single-byte body changes and missing-secret path.
- `make agent-check` + `make agent-test` clean.

**Fill in at checkpoint time:**
- Cross-repo PR link: _TBD_
- Secret source / rotation story confirmed: _TBD_
- Files touched: _TBD_

**Post-completion:** mark [`api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) "current state" section as fully landed; replace this `TODOS.md` with a short pointer to the merged PRs.

---

## Where to look when starting cold

1. This `TODOS.md` — find the first unchecked item and its checkpoint context.
2. [`wip/error-handling/api-companion-revisions.md`](wip/error-handling/api-companion-revisions.md) — what we are actually building vs. what the original spec proposed, with rationale per item. **The pipelex-api agent reads this to know what to expect.**
3. [`wip/error-handling/pipelex-changes.md`](wip/error-handling/pipelex-changes.md) — the original spec, kept for context but superseded by the revisions doc.
4. [`wip/error-handling/README.md`](wip/error-handling/README.md) — the broader error-handling landscape.
5. The most recent checkpoint's "Fill in at checkpoint time" block — running notes from the previous session.
6. `git log --oneline -20` to see the most recent landings.

The cross-repo counterpart lives in [`../pipelex-api/wip/error-handling/`](../../pipelex-api/wip/error-handling/) — open it side-by-side when reasoning about items D-2 and F.
