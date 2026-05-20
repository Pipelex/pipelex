# API-companion revisions — what we are actually building vs. the original spec

This doc captures the **deviations** the pipelex side is taking from the original spec in [`pipelex-changes.md`](pipelex-changes.md), and the **rationale** for each. Its primary audience is the `pipelex-api` agent: when you read [`pipelex-changes.md`](pipelex-changes.md) to plan how the API will consume the new pipelex primitives, read this first to know what surface to actually expect.

The execution plan that implements these revisions is [`../../TODOS.md`](../../TODOS.md).

---

## Why this exists

The original spec in [`pipelex-changes.md`](pipelex-changes.md) is **structurally sound** — every item identifies a real downstream pain and a real upstream primitive to fix it. But on close reading, several items push the very kind of consumer-side duplication, ad-hoc fallback logic, and optional-`None` plumbing that the spec itself argues against. A few items also introduce surface area earlier than it can be used, or hedge with "curate a subset, do the rest later" which leaves the codebase in an inconsistent state.

The revisions below collapse 9 items to 6, eliminate four sources of consumer-side drift, remove one "caller hand-authors a fallback" duplication pattern, drop one item as YAGNI, and stay strictly inside the repo's *no speculative future-proofing* rule (`CLAUDE.md`).

**For the API agent:** wherever the surface here disagrees with [`pipelex-changes.md`](pipelex-changes.md), **this doc is authoritative**. The spec is kept for context but is no longer the contract.

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
        return cls._declared_title or _humanize(cls.__name__)

    @classmethod
    def type_uri(cls) -> str:
        return cls._declared_type_uri or f"{_base_error_uri()}/{_kebab(cls.__name__)}"
```

Subclasses override `_declared_title` / `_declared_type_uri` only when the auto-derive is bad copy or the URI needs to point elsewhere. **Every class works out of the box.** `ErrorReport` carries both as populated string fields — consumers never see `None`.

**API consumer impact.** The API reads `report.title` and `report.type_uri` directly. No humanize helper, no kebab-case helper, no `_resolve_title_for_class_name(...)`. The `https://pipelex.dev/errors/` namespace is owned by pipelex via `get_config().errors.base_uri`.

---

### §B. Item 3 — `request_id`

**Decision taken in planning.** Field lives on `JobMetadata`, not `PipeJob`. `JobMetadata` already carries `pipeline_run_id`, `user_id`, `session_id` and threads through every activity / workflow / submitter hop via `PipeJob.job_metadata` → `PipeRunArg`. Adding it on `PipeJob` (as the spec's literal example shows) would require copying it across into `JobMetadata` anyway to make it visible to the logger context.

**Acceptance.** The API populates `JobMetadata.request_id` from its inbound `X-Request-ID` middleware once at submitter dispatch. Activity logs carry it via a `ContextVar` (same pattern as `session_id`). The current `webhook.payload["request_id"]` piggyback becomes obsolete.

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

**Revised strict redaction rule:**
- `INPUT`-domain reports → returned unchanged.
- `CONFIG` / `RUNTIME` reports → `message` replaced with `"An internal error occurred."`; `provider`, `model`, `provider_metadata`, `user_action` dropped.
- **Kept in all modes** (stable identifiers): `error_type`, `error_domain`, `error_category`, `retryable`, `title`, `type_uri`.

Both methods land in Stage 2 (was 2+4 in the spec). `to_problem_document` is callable from the API's Phase 1 directly.

**API consumer impact.** The Phase 1 builder is now ~10 lines (FastAPI Response wiring only). The envelope shape — `type`, `title`, `status`, `detail`, `instance`, extension members — comes from `report.to_problem_document(...)`. Strict mode is one kwarg. The "what does strict mode hide" rule lives in one place.

---

### §D. Item 5 — async error pipe, totality, and the Temporal data converter

This is the load-bearing item. Three sub-issues; the revisions address all of them.

#### §D.1 — "Caller hand-authors a fallback report" is duplication

**What the spec proposes.** `recover_error_report(exc)` returns `Optional[ErrorReport]`. When it returns `None` (malformed details or version skew), the caller — the workflow boundary that catches the failure — hand-authors an `ErrorReport(error_type="WorkflowFailureUnrecoverable", error_domain="runtime", retryable=False, message="...")`.

**Problem.** Every other caller that uses `recover_error_report` (the API's submitter-side recovery, the CLI on async result consumption, anyone else who lands later) duplicates this hand-author logic. The `error_type` string "WorkflowFailureUnrecoverable" doesn't correspond to a real `PipelexError` subclass, so it can't be navigated to a doc page (item 7), can't carry an auto-derived `type_uri`, and can't be matched on by pattern. The fallback is a stringly-typed escape hatch.

**What we are building instead.** A new pipelex error class — `UnrecoverableWorkflowFailureError(PipelexError)` — and `recover_error_report` becomes **total**: signature `def recover_error_report(exc: BaseException) -> ErrorReport`. When no embedded report is found or `from_dict` fails, it synthesizes the report via `UnrecoverableWorkflowFailureError(message_from_exc(exc)).to_error_report()`. One construction site, one error class, one doc page, navigable by pattern.

All three call sites in `workflow_caller.py` (`:128`, `:240`, `:292`) drop their `if error_report is not None` branches.

**API consumer impact.** When the API recovers from a Temporal workflow failure on the submitter side, it gets a usable `ErrorReport` unconditionally. No `None` to handle, no fallback to author.

#### §D.2 — `error_report_dict: dict[str, Any]` is a Temporal-shim smell

**What the spec implies.** The `DeliveryActivityArg` would carry the error as a dict because "Temporal serialization."

**Problem.** The other fields on `DeliveryActivityArg` (`pipe_output: PipeOutput | None`, `delivery_assignment: DeliveryAssignment`) don't carry `_dict` suffixes because the pipelex Temporal data converter handles them as Pydantic `BaseModel`s. Adding a `_dict` suffix telegraphs an implementation detail and is inconsistent with the rest of the file. The right answer is to make the data converter handle `ErrorReport` directly.

**Current state of the converter (verified):** `pipelex/temporal/temporal_data_converter.py` only handles `BaseModel` and `list[BaseModel]`. `ErrorReport` is a frozen Pydantic *dataclass* and will not round-trip as-is.

**What we are building instead.** Per the user's stated preference: extend the data converter (and `kajson` if necessary) to handle Pydantic dataclasses generically. The converter and `kajson` were built precisely to handle pipelex's serialization needs; extending them here benefits any future Pydantic dataclass on a workflow arg. A `tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py` case covers the round-trip before `ErrorReport` is wired into the activity arg.

**Fallback path** (only if the extension turns out to be larger than expected): convert `ErrorReport` from `@dataclass(frozen=True)` to a `BaseModel` with `model_config = ConfigDict(frozen=True)`. Smaller diff but loses dataclass ergonomics. The plan is to take the converter-extension path; this is documented as the fallback only in case the converter work surfaces something unforeseen.

#### §D.3 — Webhook payload field shape

`payload["error"] = error_report.to_dict()` — verbose disclosure by default. The API chooses strict mode at *its own* surface (HTTP response), not at the pipelex delivery boundary. The webhook is internal infrastructure between pipelex and the API; redacting it before the API has decided what to do with it would be presumptuous.

**API consumer impact.** Receiving the webhook, the API sees a full `error` dict with the same shape as `ErrorReport.to_dict()`. It can call `ErrorReport.from_dict(payload["error"])` to rehydrate, or pass it through, or redact server-side based on `ERROR_DISCLOSURE`.

---

### §E. Item 7 — per-class doc pages

No structural change from the spec. The improvement is that `cls.title()` and `cls.type_uri()` from item A are total (always populated), so the generator never has to fall back to placeholder content. Every page has a real title and a stable URL anchor.

---

### §F. Item 8 — `query_pipeline_state(...)` — **dropped**

**What the spec proposes.** A pipelex-level async function `query_pipeline_state(pipeline_run_id) -> PipelineState` that reads Temporal workflow history and returns a typed state for a future `GET /api/v1/pipeline/{run_id}` endpoint.

**Problem.** The spec itself flags this as future-facing: *"Not blocking the current API work... The status-query is a different use case (polling, not push) that no current consumer needs yet."* That is the textbook definition of speculative work. Repo `CLAUDE.md` is explicit: *"Don't add features... beyond what the task requires. Don't design for hypothetical future requirements."*

The risk of designing it now without a concrete consumer is that the typed state shape (`PipelineState` fields, naming, semantics for cancelled / timed-out workflows, how to surface partial progress) gets locked in by the API agent's assumptions rather than by a real client's needs.

**What we are doing instead.** Drop from this pass. When the first concrete polling consumer materializes — with a real spec for what fields it needs — the work picks up with clear requirements. The `recover_error_report` primitive (now total per item D-1) is already in place for that future use; only the workflow-history reading and the typed state shape are deferred.

**API consumer impact.** The webhook path is the supported async pattern. A future polling endpoint requires fresh design once a client asks for it.

---

### §G. Item 9 — webhook signature

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

> **For the API agent:** check this section first to know what's actually available. It is updated at every checkpoint in [`../../TODOS.md`](../../TODOS.md).

- [ ] **Stage 1 — Foundations.** Items A + B.
- [ ] **Stage 2 — Rendering primitives + total recovery.** Items C + D-1.
- [ ] **Stage 3 — Async error pipe.** Item D-2 (the unblock for API Phase 4).
- [ ] **Stage 4 — DX polish.** Item E.
- [ ] **Stage 5 — Security tightening.** Item F (cross-repo).

Nothing landed yet on this branch (`feature/API-readiness`). When something lands, this list will tick green and a "What landed" subsection will appear below with file:line references the API agent can read against.
