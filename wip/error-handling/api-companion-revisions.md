# API-companion revisions — what we are actually building vs. the original spec

This doc captures the **deviations** the pipelex side is taking from the original spec in [`changes-for-api-early-draft.md`](changes-for-api-early-draft.md), and the **rationale** for each. Its primary audience is the `pipelex-api` agent: when you read [`changes-for-api-early-draft.md`](changes-for-api-early-draft.md) to plan how the API will consume the new pipelex primitives, read this first to know what surface to actually expect.

The execution plan that implemented these revisions is the now-archived [`archive-todos.md`](archive-todos.md).

---

## Why this exists

The original spec in [`changes-for-api-early-draft.md`](changes-for-api-early-draft.md) is **structurally sound** — every item identifies a real downstream pain and a real upstream primitive to fix it. But on close reading, several items push the very kind of consumer-side duplication, ad-hoc fallback logic, and optional-`None` plumbing that the spec itself argues against. A few items also introduce surface area earlier than it can be used, or hedge with "curate a subset, do the rest later" which leaves the codebase in an inconsistent state.

The revisions below collapse and re-scope the original items (see the mapping table next), eliminate the consumer-side drift sources it introduced, remove the "caller hand-authors a fallback" duplication pattern, drop the speculative item as YAGNI, and stay strictly inside the repo's *no speculative future-proofing* rule (`CLAUDE.md`).

**For the API agent:** wherever the surface here disagrees with [`changes-for-api-early-draft.md`](changes-for-api-early-draft.md), **this doc is authoritative**. The spec is kept for context but is no longer the contract.

---

## Mapping: original items → revised items

| Original spec items | Revised item | Stage |
|---|---|---|
| 1 (`title`) + 2 (`type_uri`) | **Item A** — `PipelexError.title()` / `type_uri()` classmethods with auto-derive defaults | 1 |
| 3 (`request_id`) | **Item B** — `request_id` on `JobMetadata` | 1 |
| 4 (`to_strict_dict`) + 6 (`to_problem_document`) | **Item C** — `to_dict(disclosure_mode=)` + `to_problem_document(...)` | 2 |
| 5 (caller-recovers + caller-hand-authors fallback) — *part 1* | **Item D-1** — make `recover_error_report` total | 2 |
| 5 — *part 2* | **Item D-2** — thread `ErrorReport` to the webhook | 3 |
| 7 (per-class doc pages) | **Item E** | 4 |
| **8 (`query_pipeline_state`)** | **dropped** — speculative future work | — |
| 9 (full-payload webhook signature) | **Item F** | 5 |

---

## Per-item revisions and rationale

### §A. Items 1+2 — `title` / `type_uri` ownership

**What the spec proposes.** Add `ClassVar[str | None]` attributes defaulting to `None`. When `None`, "downstream consumers fall back to humanizing the class name" / "auto-derive `<base>/<kebab-case classname>` from a pipelex-config-provided base URI."

**Problem.** This is exactly the duplication the spec's own *Why* section argues against ("Curating titles API-side creates drift"). If pipelex doesn't own the auto-derive, every consumer (the API, the CLI, the agent CLI, future SDKs) re-implements humanize-from-classname and kebab-case. The drift moves from "curated copy" to "humanize implementation" — it doesn't go away.

**What we are building instead.**

```python
class PipelexError(Exception):
    _declared_title: ClassVar[str | None] = None
    _declared_type_uri: ClassVar[str | None] = None

    @classmethod
    def title(cls) -> str:
        # read only the class's OWN body — a curated title is never inherited
        declared = cls.__dict__.get("_declared_title")
        return declared if isinstance(declared, str) else _humanize(cls.__name__)

    @classmethod
    def type_uri(cls) -> str:
        declared = cls.__dict__.get("_declared_type_uri")
        if isinstance(declared, str):
            return declared
        return f"{_base_error_uri()}/{_kebab(cls.__name__)}/"
```

Subclasses override `_declared_title` / `_declared_type_uri` only when the auto-derive is bad copy or the URI needs to point elsewhere — and the override is read from the class's own body, so a subclass never silently inherits an ancestor's curated value (see [What landed in Stage 1](#what-landed-in-stage-1)). **Every class works out of the box.** `ErrorReport` carries both as populated string fields — consumers never see `None`.

**API consumer impact.** The API reads `report.title` and `report.type_uri` directly. No humanize helper, no kebab-case helper, no `_resolve_title_for_class_name(...)`. The `https://docs.pipelex.com/latest/errors` namespace is owned by pipelex via the `URLs.error_docs_base` constant (`pipelex/urls.py`).

---

### §B. Item 3 — `request_id`

**Decision taken in planning.** Field lives on `JobMetadata`, not `PipeJob`. `JobMetadata` already carries `pipeline_run_id`, `user_id`, `session_id` and threads through every activity / workflow / submitter hop via `PipeJob.job_metadata` → `PipeRunArg`. Adding it on `PipeJob` (as the spec's literal example shows) would require copying it across into `JobMetadata` anyway to make it visible to the logger context.

**Acceptance.** The API populates `JobMetadata.request_id` from its inbound `X-Request-ID` middleware once at submitter dispatch. From there `request_id` rides on `JobMetadata` across every Temporal hop and is threaded **explicitly** into the worker-side log calls — **not** via a `ContextVar`. A `ContextVar` is process-local and does not survive the Temporal activity/workflow serialization boundary, so it cannot carry a correlation id from the submitter process to a worker running in another process. The worker-side wiring landed in TODOS Phase 2 (2026-05-22): `WfPipeRun` / `WfPipeRouter` build a per-invocation `WorkflowLog` bound to `job_metadata.request_id` at entry, so every workflow log record they emit carries `request_id` in its `extra` dict. The current `webhook.payload["request_id"]` piggyback becomes obsolete.

---

### §C. Items 4+6 — disclosure modes and rendering

**What the spec proposes.** Split into two methods: `ErrorReport.to_strict_dict()` at Stage 2, then `ErrorReport.to_problem_document(disclosure_mode=...)` at Stage 4. The redaction rule for strict mode drops `user_action`, `provider`, `model`, `provider_metadata` *and* replaces `message` with a fixed string.

**Problems.**

1. **The `DisclosureMode` enum is introduced at Stage 2 but its only real consumer is at Stage 4.** Either merge the work or parameterize `to_dict` directly. The spec itself hedges with "Add a method (or parameterize `to_dict`)" — the parameterized version is the right call.
2. **Stage placement of `to_problem_document` is wrong.** The spec defers it to Stage 4 with the reasoning "the API's Phase 1 builder needs ~30 lines anyway." But those 30 lines are about FastAPI Response wiring (headers, content type, status code) — the **dict shape** is the reusable part, and if pipelex doesn't own it, the API builds its own envelope in Phase 1 and creates the very drift item 6 is meant to prevent.
3. **The redaction rule strips `title`.** RFC 7807 §3.1.4: `title` is "the same for occurrences of the problem" — a *stable type identifier*, not sensitive data. Same for `type_uri`, `error_type`, `error_domain`, `error_category`, `retryable`. Redacting these breaks the very spec the API is trying to comply with. The redaction should target `message` (can contain paths, prompts, user data) and implementation details (`provider`, `model`, `provider_metadata`, `user_action.detail` which can contain operator-specific advice).

**What we are building instead.**

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

**Strict redaction rule:**
- `provider`, `model`, `provider_metadata` → always dropped, whatever the `error_domain`.
- A report flagged `caller_facing_message` (set by error classes that author caller-facing copy — `PipelexInterpreterError`, `ValidateBundleError`) → keeps its `message` and `user_action`.
- Every other report → `message` replaced with `"An internal error occurred."`, `user_action` dropped.
- **Kept in all modes** (stable identifiers): `error_type`, `error_domain`, `error_category`, `retryable`, `title`, `type_uri`.

> **Gap closed (2026-05-22, TODOS Phase 1).** STRICT originally keyed its `message` passthrough on `error_domain == INPUT`, which is *inherited* up the `__cause__` chain — so a domain-less wrapper raised `from` an `INPUT` cause could leak its own (non-caller-facing) `message`, and `to_problem_document(STRICT)` could echo provider metadata for `INPUT` reports. The passthrough now keys on a per-class `caller_facing_message` flag (message *provenance*, not inherited classification) and provider metadata is stripped unconditionally. See [`track-strict-disclosure-input-domain-gap.md`](track-strict-disclosure-input-domain-gap.md).

Both methods land in Stage 2 (was 2+4 in the spec). `to_problem_document` is callable from the API's Phase 1 directly.

**API consumer impact.** The Phase 1 builder is now ~10 lines (FastAPI Response wiring only). The envelope shape — `type`, `title`, `status`, `detail`, `instance`, extension members — comes from `report.to_problem_document(...)`. Strict mode is one kwarg. The "what does strict mode hide" rule lives in one place.

---

### §D. Item 5 — async error pipe, totality, and the Temporal data converter

This is the load-bearing item. Three sub-issues; the revisions address all of them.

**Numbering note.** The `§D.x` subsections below are *sub-issues*, not revised items. §D.1 is **Item D-1** (totality, Stage 2); §D.2 and §D.3 together are **Item D-2** (`ErrorReport` threaded to the webhook as a typed field, Stage 3). There is no "Item D-3".

#### §D.1 — "Caller hand-authors a fallback report" is duplication

**What the spec proposes.** `recover_error_report(exc)` returns `Optional[ErrorReport]`. When it returns `None` (malformed details or version skew), the caller — the workflow boundary that catches the failure — hand-authors an `ErrorReport(error_type="WorkflowFailureUnrecoverable", error_domain="runtime", retryable=False, message="...")`.

**Problem.** Every other caller that uses `recover_error_report` (the API's submitter-side recovery, the CLI on async result consumption, anyone else who lands later) duplicates this hand-author logic. The `error_type` string "WorkflowFailureUnrecoverable" doesn't correspond to a real `PipelexError` subclass, so it can't be navigated to a doc page (item 7), can't carry an auto-derived `type_uri`, and can't be matched on by pattern. The fallback is a stringly-typed escape hatch.

**What we are building instead.** A new pipelex error class — `UnrecoverableWorkflowFailureError(TemporalFlowError)`, a `PipelexError` subclass — and `recover_error_report` becomes **total**: signature `def recover_error_report(exc: BaseException) -> ErrorReport`. When no embedded report is found, it synthesizes the report via `UnrecoverableWorkflowFailureError(message_from_exc(exc)).to_error_report()`. One construction site, one error class, one doc page, navigable by pattern. A report dict that *is* found but fails `from_dict` validation is an internal contract bug — within one deploy the activity bridge and the submitter share the schema — and is also synthesized into the same `UnrecoverableWorkflowFailureError` fallback (with an `[error report failed schema validation]` marker on the message) so the failure webhook still fires before the workflow surfaces the contract bug. The Temporal integration ships fresh, so there is no prior on-wire schema to stay compatible with.

All three call sites in `workflow_caller.py` (`execute_workflow` / `execute_child_workflow` / `start_child_workflow`) drop their `if error_report is not None` branches.

**API consumer impact.** When the API recovers from a Temporal workflow failure on the submitter side, it gets a usable `ErrorReport` unconditionally. No `None` to handle, no fallback to author.

#### §D.2 — `error_report_dict: dict[str, Any]` is a Temporal-shim smell

**What the spec implies.** The `DeliveryActivityArg` would carry the error as a dict because "Temporal serialization."

**Problem.** The other fields on `DeliveryActivityArg` (`pipe_output: PipeOutput | None`, `delivery_assignment: DeliveryAssignment`) don't carry `_dict` suffixes because the pipelex Temporal data converter handles them as Pydantic `BaseModel`s. Adding a `_dict` suffix telegraphs an implementation detail and is inconsistent with the rest of the file. `ErrorReport` should cross the activity boundary as a typed field, like every other field on the arg.

**What we built.** `ErrorReport` was converted from a frozen Pydantic `@dataclass` to a `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`. The Temporal data converter then handles it with **no converter surgery**: the already-shipped `BaseModelPayloadConverter._unwrap_optional_base_model` resolves the `ErrorReport | None` field directly. `DeliveryActivityArg.error_report: ErrorReport | None` is a plain typed field — no `_dict` suffix, no shim. A `tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py` case covers the round-trip before `ErrorReport` is wired into the activity arg.

**Why this, not extending the converter.** The alternative considered was teaching the data converter (and `kajson`) to round-trip Pydantic dataclasses generically. The `BaseModel` conversion turned out strictly cleaner: it reuses the converter's existing `BaseModel` path instead of adding a new one, it is a smaller diff, and `extra="forbid"` gives `from_dict` the strict-schema validation the §D.1 recovery path depends on. The dataclass-vs-`BaseModel` ergonomics difference is negligible for a frozen value type.

#### §D.3 — Webhook payload field shape

`payload["error"] = error_report.to_dict()` — verbose disclosure by default. The API chooses strict mode at *its own* surface (HTTP response), not at the pipelex delivery boundary; redacting the payload before the receiver has decided what to do with it would be presumptuous. The webhook target URL is caller-supplied, so a VERBOSE `error` dict reaches an endpoint pipelex does not control — but that endpoint belongs to the run's own caller, who already owns the run and its inputs. VERBOSE is therefore the receiver's data to redact, not pipelex's — accepted by design. Webhook signing (Item F / Stage 5) is orthogonal: it authenticates the webhook's origin so the receiver can trust it, but does not change what the payload discloses.

**API consumer impact.** Receiving the webhook, the API sees a full `error` dict with the same shape as `ErrorReport.to_dict()`. It can call `ErrorReport.from_dict(payload["error"])` to rehydrate, or pass it through, or redact server-side based on `ERROR_DISCLOSURE`.

---

### §E. Item 7 — per-class doc pages

No structural change from the spec. The improvement is that `cls.title()` and `cls.type_uri()` from item A are total (always populated), so the generator never has to fall back to placeholder content. Every page has a real title and a stable URL anchor.

**One material deviation, settled at landing time.** The original plan had `base_uri` defaulting to `https://pipelex.dev/errors` — a domain that does not actually serve these pages. Retargeted at landing to `https://docs.pipelex.com/latest/errors`, the live MkDocs + mike docs site. The `/latest/` alias is mike's canonical pointer at current stable, forced via `docs/overrides/main.html` — a `type` URI emitted by any deployed version always lands on up-to-date docs. `PipelexError.type_uri()` now appends a trailing slash (`<base>/<slug>/`) to match the canonical form MkDocs serves with `use_directory_urls: true` — clients dereferencing the URI hit the page directly without a 301. API consumers should treat `type_uri` as opaque and not strip or normalize the trailing slash.

---

### Dropped — Item 8 — `query_pipeline_state(...)`

This item is **dropped** from the plan. It is not assigned a revised-item letter — the `§A`–`§F` sections cover `Item A`–`Item F` (`Item D` itself splits into `D-1` / `D-2`; see the [mapping table](#mapping-original-items--revised-items)).

**What the spec proposes.** A pipelex-level async function `query_pipeline_state(pipeline_run_id) -> PipelineState` that reads Temporal workflow history and returns a typed state for a future `GET /api/v1/pipeline/{run_id}` endpoint.

**Problem.** The spec itself flags this as future-facing: *"Not blocking the current API work... The status-query is a different use case (polling, not push) that no current consumer needs yet."* That is the textbook definition of speculative work. Repo `CLAUDE.md` is explicit: *"Don't add features... beyond what the task requires. Don't design for hypothetical future requirements."*

The risk of designing it now without a concrete consumer is that the typed state shape (`PipelineState` fields, naming, semantics for cancelled / timed-out workflows, how to surface partial progress) gets locked in by the API agent's assumptions rather than by a real client's needs.

**What we are doing instead.** Drop from this pass. When the first concrete polling consumer materializes — with a real spec for what fields it needs — the work picks up with clear requirements. The `recover_error_report` primitive (now total per item D-1) is already in place for that future use; only the workflow-history reading and the typed state shape are deferred.

**API consumer impact.** The webhook path is the supported async pattern. A future polling endpoint requires fresh design once a client asks for it.

---

### §F. Item 9 — webhook signature

No structural change from the spec. One implementation note: the per-deployment signing secret lives in pipelex config (`get_config().pipeline_execution_config.webhook_signing_secret`) with an environment-variable fallback for ops convenience. The cross-repo PRs land in coordinated lockstep.

---

## Cross-cutting themes

These show up in multiple items above; collecting them here so the API agent can recognize the patterns when reviewing pipelex PRs.

- **Pipelex owns the defaults.** If a primitive has an obvious sensible default (humanize a class name, kebab-case a class name, "an internal error occurred" placeholder), the default lives in pipelex and is returned as a populated value, not as `None` that consumers fill in. The only `None`s consumers see are for genuinely-absent data (no provider involved, no `user_action` declared).
- **Total functions over partial ones.** `recover_error_report` returns an `ErrorReport`, not `ErrorReport | None`. `title()` returns a `str`, not `str | None`. Each consumer is one branch simpler.
- **No backward-compat shims.** New optional kwargs default to the natural empty value because *that is the natural empty value*, not to preserve old callers. The project explicitly does not have a deprecation transition period.
- **No speculative surface.** We don't introduce surface that will be used "later." If item 6 is genuinely needed in Stage 2, it lands in Stage 2. If item 8 isn't needed by any current consumer, it doesn't land.

---

## Current state

> **For the API agent:** check this section first to know what's actually available. The full per-stage execution ledger is archived at [`archive-todos.md`](archive-todos.md).

- [x] **Stage 1 — Foundations.** Items A + B.
- [x] **Stage 2 — Rendering primitives + total recovery.** Items C + D-1.
- [x] **Stage 3 — Async error pipe.** Item D-2 (the unblock for API Phase 4).
- [x] **Stage 4 — DX polish.** Item E.
- [ ] **Stage 5 — Security tightening.** Item F (cross-repo, tracked at [`../security/webhook-signing.md`](../security/webhook-signing.md)).

**Net to the API team:** the error-handling refactor on the pipelex side is landed — Stages 1-4 ship in PR #933 (PR #931 was the prior staging branch and was closed unmerged; the work was replayed and finalized on `feature/API-readiness-2`). API Phases 0/1/4/5 are unblocked. One thing remains on the pipelex side:

- **Webhook signing (Stage 5 / Item F)** — the cross-repo security track at [`../security/webhook-signing.md`](../security/webhook-signing.md), independent of the rest of this plan, landing on its own schedule.

The post-review follow-ups — a `/review` pass surfaced a small set of in-repo finalizations, sequenced in the archived [`archive-todos-api-readiness-2.md`](archive-todos-api-readiness-2.md) — all landed 2026-05-22 on `feature/API-readiness-2`: the STRICT-disclosure INPUT-domain leak (Phase 1), the `request_id` log wiring (§B; Phase 2), the webhook reserved-key collision (Phase 3), and the test-coverage backfill (Phase 4).

### What landed in Stage 1

Available now:

- **`PipelexError.title()` / `PipelexError.type_uri()`** (`pipelex/base_exceptions.py`) — classmethods returning a populated `str`. Auto-derive from the class name unless a subclass declares `_declared_title` / `_declared_type_uri` directly in its own body (inheritance is intentionally bypassed). Curated `_declared_title` overrides shipped for high-traffic base classes.
- **`ErrorReport.title` and `ErrorReport.type_uri`** — both required `str`. Every `to_error_report()` call populates them. Round-trips through `to_dict` / `from_dict`. `from_dict` raises `ValidationError` on missing fields (the path that Stage 2 Item D-1's `recover_error_report` synthesizes into `UnrecoverableWorkflowFailureError`).
- **`URLs.error_docs_base`** (`pipelex/urls.py`) — the base URI for every error `type_uri`, a hardcoded constant (`"https://docs.pipelex.com/latest/errors"`). `type_uri()` is a pure function: it reads only this constant, so it is safe to call before Pipelex boot and inside Temporal workflow code. A fork that needs a different host patches the constant or declares a per-class `_declared_type_uri`.
- **`pascal_case_to_kebab`** (`pipelex/tools/misc/string_utils.py`) — acronym-aware kebab conversion (`"APIError" -> "api-error"`, `"V2APIError" -> "v2-api-error"`, `"OAuth2" -> "o-auth2"`).
- **`JobMetadata.request_id: str | None`** (`pipelex/pipeline/job_metadata.py`) — round-trips through `model_dump_json`, distinct from `ProviderErrorMetadata.request_id` (the provider-side request id) which keeps its name.
- **`pipeline_run_setup(..., request_id="...")`** (`pipelex/pipeline/pipeline_run_setup.py`) — kwarg threaded into the constructed `JobMetadata`. The current `webhook.payload["request_id"]` piggyback on the API side is now obsolete; consumers should set `request_id` at dispatch time and read it back off `arg.<path>.job_metadata.request_id`.
- **`WorkflowLog` / `ActivityLog`** (`pipelex/temporal/log_temporal.py`) — every level (`verbose` / `debug` / `dev` / `info` / `warning` / `error` / `critical`) attaches the helper's bound `request_id` to the Temporal log record via `extra={"request_id": ...}`. Stage 1 shipped a per-method `request_id` kwarg here; TODOS Phase 2 (2026-05-22) replaced it with a per-invocation bound helper — `WfPipeRun` / `WfPipeRouter` build a `WorkflowLog` from `job_metadata.request_id` at entry, so worker log records now carry the `request_id` end to end.

**Update — `type_uri()` is now a pure constant.** Stage 1 originally read the base URI through an `ErrorManager` singleton holding an `ErrorsConfig` — a workaround for the import cycle a lazy `get_config()` call inside the method would have created. That whole machinery (`ErrorManager`, `ErrorsConfig`, the `[errors_config]` config block) was later removed: the `type` URI is a stable identifier per RFC 7807, so making it configurable was over-engineering, and the mutable read leaked into Temporal workflow determinism (the base URI rode into workflow history via a synthesized `UnrecoverableWorkflowFailureError`). `type_uri()` now reads the `URLs.error_docs_base` constant directly — a pure function, no boot dependency, no static cycle. API consumers see no difference.

**What `ErrorReport` looks like now.** Still a `@pydantic.dataclasses.dataclass(frozen=True, ...)` at the end of Stage 1; the conversion to `BaseModel` lands in Stage 3 Item D-2 as a prereq for crossing the Temporal activity boundary as a typed field. The Stage 2 work (`to_dict(disclosure_mode=...)` / `to_problem_document(...)`) lands on the dataclass form.

### What landed in Stage 2

Available now:

- **`DisclosureMode` enum** (`pipelex/base_exceptions.py`) — `VERBOSE` / `STRICT`. The contract is pinned on the enum's own docstring: STRICT is a *classification-projection*, **not a path-leak shield**. STRICT always drops `provider` / `model` / `provider_metadata`, then redacts `message` by *provenance*: a report flagged `caller_facing_message` (set by error classes that author caller-facing copy — `PipelexInterpreterError` / `ValidateBundleError`) keeps its `message` and `user_action`; every other report drops `user_action` and replaces `message` with `"An internal error occurred."`, keeping the stable identifiers (`error_type` / `error_domain` / `error_category` / `retryable` / `title` / `type_uri`). The passthrough keys on the per-class flag, not `error_domain` — refined post-#931 from the original Stage 2 `error_domain == INPUT` keying (TODOS Phase 1; see the gap note above).
- **`ErrorReport.to_dict(disclosure_mode=DisclosureMode.VERBOSE)`** — projects the report through the disclosure mode. `VERBOSE` round-trips through `from_dict` exactly; `STRICT` is lossy by design. Default is `VERBOSE` so existing internal-trust callers (webhook payloads, Temporal details) are unaffected.
- **`ErrorReport.to_problem_document(*, instance=None, request_id=None, disclosure_mode=VERBOSE)`** — returns a plain dict in RFC 7807 shape. `type` ← `type_uri`, `title` ← `title`, `status` ← `http_status`, `detail` ← `message` (subject to disclosure-mode redaction). The pipelex-native classification fields ride as extension members; `type_uri` and `title` are mapped — NOT echoed — so the returned dict contains exactly one `title` key. `request_id` and `instance` ride as extensions only when the caller supplies them. The runtime stays HTTP-agnostic — no FastAPI/Starlette import.
- **`recover_error_report(exc: BaseException) -> ErrorReport`** (`pipelex/temporal/tprl/temporal_error.py`) — total. When the failure carries no embedded report, the function synthesizes `UnrecoverableWorkflowFailureError(_message_from_exc(exc)).to_error_report()`. A report dict that *is* found but fails `from_dict` validation is an internal contract bug — the activity bridge and the submitter share the schema within one deploy — and is also synthesized into the same `UnrecoverableWorkflowFailureError` fallback, with the recovered message plus an `[error report failed schema validation]` marker, so failure-webhook delivery stays intact (the workflow still fails afterwards, keeping the contract bug visible). `UnrecoverableWorkflowFailureError` lives in `pipelex/temporal/exceptions.py` next to `WorkflowExecutionError` etc., with `error_domain=RUNTIME` and `_declared_title="Unrecoverable workflow failure"`. Callers in `workflow_caller.py` (the three former `if error_report is not None` branches at `execute_workflow` / `execute_child_workflow` / `start_child_workflow`) now treat the return as always-usable.

**One deviation from the spec's `message_from_exc`.** The plan specified "outer Temporal failure's message if non-empty, else `repr(exc)`". Implemented instead as a `__cause__`-chain walk that keeps the deepest non-empty message — because `WorkflowFailureError` always carries the generic outer text `"Workflow execution failed"`, which would defeat the round-3 P2 pin (the test asserts the synthesized message "contains the underlying exception text"). The walk surfaces the worker-side cause text (`RuntimeError("worker crashed hard")` → message contains `"worker crashed hard"`) while still falling back to `repr(exc)` when every node in the chain has an empty message. Same observable contract for callers; strictly more informative messages.

**User-visible behavior change at the unrecoverable path.** After Item D-1, `WorkflowExecutionError.message` on the no-report path changes from the Pipelex-framed `"Failed to execute workflow X"` / `"Application error in child workflow X"` to the synthesized `_message_from_exc(exc)` text. This is intentional — strictly more diagnostic — and is pinned by the rewritten `test_workflow_failure_without_report_synthesizes_unrecoverable` test. The legacy framing strings are gone on the `WorkflowFailureError` and `isinstance(exc.cause, ApplicationError)` paths. They remain on the `WorkflowAlreadyStartedError` / `RPCError` / non-`ApplicationError`-cause paths, because those branches do not call `recover_error_report`.

### What landed in Stage 3

Available now:

- **`ErrorReport` is a `BaseModel`** (`pipelex/base_exceptions.py`) — `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`. `to_dict` uses `self.model_dump(exclude_none=True)`; `from_dict` uses `cls.model_validate(data)`. The frozen contract now raises `pydantic.ValidationError` (not `dataclasses.FrozenInstanceError`) on mutation attempts — caller-visible if anyone caught the specific dataclass error. Tests updated to match.
- **`DeliveryExecutor.execute(error_report=...)`** (`pipelex/pipe_run/delivery_executor.py`) — accepts `ErrorReport | None`; when non-None, the webhook payload includes `error = report.to_dict(DisclosureMode.VERBOSE)`. Receivers (the API) rehydrate losslessly via `ErrorReport.from_dict(payload["error"])`. The webhook stays the only mechanism for surfacing the report — the storage path does NOT serialize it as a file. The disclosure choice (VERBOSE on the wire) is locked here; the API decides what to re-expose to its own clients (it can render strict via `to_problem_document(disclosure_mode=STRICT)`).
- **`DeliveryActivityArg.error_report: ErrorReport | None`** (`pipelex/temporal/tprl_pipe/act_deliver.py`) — typed BaseModel field. No `_dict` shim. The existing `BaseModelPayloadConverter._unwrap_optional_base_model` (already shipped in Stage 1) handles the `ErrorReport | None` field directly with no converter surgery.
- **`wf_pipe_run.py` recovers and threads the report.** On the `ChildWorkflowError` catch, calls `recover_error_report(exc.cause if exc.cause is not None else exc)` (total since Item D-1), uses it to construct `WorkflowExecutionError("WfPipeRouter failed", error_report=report)` AND threads it into `DeliveryActivityArg(error_report=report)`. The outer Temporal wrap therefore does NOT drop the inner classification — the submitter-side `WorkflowExecutionError.to_error_report()` carries the same `error_type` / `error_category` / `retryable` / `model` / `provider` / `user_action` / `title` / `type_uri` the worker saw. Pinned by the new end-to-end full-chain test.
- **Direct-mode `PipeRun` (`pipelex/pipe_run/pipe_run.py`) threads the report too.** Captures `error_report = exc.to_error_report()` when the caught exception is a `PipelexError`, passes it to `DeliveryExecutor.execute`. The local / Temporal parity now holds at the delivery boundary — a sync-mode failure surfaces the same `error` dict on the webhook as a Temporal-mode failure. (This was an additive deviation from the plan's strict reading: the plan called out only the Temporal path, but the D-2 acceptance criterion implies parity, so the direct path was updated too. Non-`PipelexError` exceptions still surface no report, matching existing in-process semantics.)
**One additive deviation.** The plan localized the threading to the Temporal path. The direct-mode `PipeRun` was also updated for parity (see above). Same observable contract for API consumers in both modes.

**Pre-flight that the activity arg change relies on.** `tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py::TestPayloadCodecRoundTrip::test_error_report_round_trips_through_activity` lands as a new test case that round-trips an `ErrorReport` (with populated `UserAction` + `ProviderErrorMetadata`) through a workflow → activity → return hop, verifying the BaseModel converter handles it directly. The plan's ordering (round-trip test before activity arg change) is preserved within the same commit set.

### What landed in Stage 4

Available now:

- **Error `type_uri` base is `https://docs.pipelex.com/latest/errors`** (`URLs.error_docs_base` in `pipelex/urls.py`) — the `/latest/` alias is mike's canonical pointer at current stable; canonical URLs are forced to `/latest/` via `docs/overrides/main.html`. A fork hosting its own error docs patches the constant.
- **`PipelexError.type_uri()` emits a trailing slash** (`pipelex/base_exceptions.py`) — form is `<base>/<kebab-class-name>/`. Matches the canonical URL MkDocs serves with `use_directory_urls: true` (verified against the built `<link rel="canonical">` of the deployed page). Clients dereferencing the URI now hit the docs page directly — no 301 round-trip. Treat `type_uri` as opaque on the API side; do NOT strip or normalize the trailing slash.
- **`docs/errors/<kebab-class-name>.md`** — one generated page per non-test `PipelexError` subclass. Each page carries the class identity table (`error_type`, `title`, `type_uri`, `error_domain`, defining module, parent-class link, class-level `user_action` when declared), a docstring fragment when present, and a back-link to the Error Model overview. Stamped with `<!-- pipelex:generated -->`. Maintainers can claim a page for hand-editing by adding `<!-- pipelex:authored -->` as a standalone line; the generator then preserves it across runs. A landing `docs/errors/index.md` lists every page grouped by top-level `PipelexError` branch.
- **`pipelex-dev generate-error-pages`** (`pipelex/cli/dev_cli/commands/generate_error_pages_cmd.py`) — internal CLI command to regenerate the pages. Quiet status line via `--quiet`; custom output dir via `--output DIR` (defaults to `docs/errors/`). Bootstraps Pipelex for parity with other dev CLI commands and to surface setup errors; discovery itself is handled by `iter_pipelex_error_subclasses`; tears down on exit.
- **`pipelex/errors/error_pages_generator.py::iter_pipelex_error_subclasses`** — yields every `PipelexError` subclass. Calls `_force_load_all_error_modules()` (a `functools.cache`-d helper) on first invocation to rglob the package for `exceptions.py` / `*_exceptions.py` modules and force-import each. Discovery is complete (AST set = runtime set, enforced by `tests/unit/pipelex/errors/test_error_class_location_convention.py`); the helper runs only inside dev/test-time consumers (the docs generator and the URI uniqueness test), never on production bootstrap.
- **`mkdocs.yml` updates** — added a `not_in_nav` directive whitelisting `errors/*.md` (except `errors/index.md`) and `CLAUDE.md` so `make docs-check` (= `mkdocs build --strict`) finishes with zero INFO/WARNING/ERROR; added "Reference > Error Reference" pointing at `errors/index.md`.
- **Pre-existing bug fix carried in this stage.** `pipelex/core/pipes/inputs/input_stuff_specs_factory.py` was shadowing `InputStuffSpecsFactoryError` with a local declaration that bypassed the canonical class in `pipelex/core/pipes/inputs/exceptions.py`. Two distinct class objects with the same name existed. Consolidated to one — the factory module now re-exports the canonical class via `__all__`; test imports keep working with no callsite changes.

**One deviation from the plan**, both already documented in §E above: `base_uri` defaulted to the live docs host (not `pipelex.dev`), and `type_uri()` emits a trailing slash. Pure URL-shape changes; no other contract shifts. The trailing slash is the only thing the API team needs to be aware of when comparing strings against `type_uri` values.
