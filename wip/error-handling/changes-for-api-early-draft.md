# Pipelex changes — companion work for the API error-handling refactor

Changes to the **pipelex** library to land in parallel with (and largely before) the `pipelex-api` error-handling refactor. The goal is to expose the right primitives upstream so the API consumes them cleanly instead of duplicating logic, working around missing fields, or stalling Phase 4.

This is **not a follow-up list.** It is the pipelex-side workplan for the same integration. Done well, the API plan in [../../TODOS.md](../../TODOS.md) reads as straight consumer code with no compensating logic. Done poorly, the API plan accumulates small workarounds that the next consumer (CLI, agent CLI, future SDK) will have to either re-write or refactor away.

Each item names a concrete API surface in pipelex, the downstream pain it removes, and a landing stage. File-path references with `pipelex/` are pipelex; with `api/` are this repo.

The list is intentionally specific. "Pipelex should be better at errors" is not actionable. "`ErrorReport.to_strict_dict()` returns a dict with `CONFIG`/`RUNTIME` domain fields redacted per a fixed rule" is.

---

## Landing stages

Stages map to **dependencies on the `pipelex-api` plan**, not effort. An item in Stage 2 takes the same engineering time as one in Stage 1 — it just has fewer downstream consumers waiting on it.

- **Stage 1 — Foundations (lands before pipelex-api Phase 0).** Class-level metadata on `PipelexError` subclasses. The API consumes these on day one of Phase 0 instead of building a humanize-from-classname fallback.
- **Stage 2 — Rendering primitives (lands before pipelex-api Phase 1).** `ErrorReport` gains methods that turn the structured report into presentational shapes. The API consumes them in its problem-document builder.
- **Stage 3 — Async error pipe (lands before pipelex-api Phase 4).** `DeliveryExecutor` carries the failure report through to the webhook. The async path becomes lossless.
- **Stage 4 — DX polish (lands alongside pipelex-api Phase 5).** Per-class docs anchors and the optional rendering escape hatch.
- **Stage 5 — Future-facing (lands when needed, not blocking).** Sync status-query primitive — designed now so the future `GET /api/v1/pipeline/{run_id}` endpoint has somewhere clean to land.
- **Stage 6 — Security tightening (independent track, do soon).** Webhook signature scope. Pre-existing weakness made more visible by carrying richer payloads.

---

## Stage 1 — Foundations

### 1. `PipelexError.title: ClassVar[str | None]`

**Where:** `pipelex/base_exceptions.py:114` (the `PipelexError` base class).

**What.** Let `PipelexError` subclasses declare a short human title via a class attribute. Defaults to `None`, in which case downstream consumers fall back to humanizing the class name.

```python
class PipelexError(Exception):
    error_domain: ClassVar[ErrorDomain | None] = None
    user_action: ClassVar[UserAction | None] = None
    title: ClassVar[str | None] = None  # NEW

class EnvVarNotFoundError(PipelexError):
    error_domain = ErrorDomain.CONFIG
    title = "Environment variable not set"

class LLMCompletionError(CogtError):
    title = "LLM provider returned an error"
```

`PipelexError.to_error_report()` sets `report.title = type(self).title` when defined.

`ErrorReport` carries it as a new optional field:

```python
@dataclass(frozen=True, ...)
class ErrorReport:
    error_type: str
    message: str
    title: str | None = None  # NEW
    ...
```

**Why.** RFC 7807 §3.1.4 says `title` should be a "short, human-readable summary of the problem type" that is "the same for occurrences of the problem." The API uses `title` directly in the RFC 7807 envelope. Today the API would auto-derive from the class name (`EnvVarNotFoundError` → `"Env Var Not Found Error"`) — stable but awkward copy. Curating titles API-side creates drift when pipelex adds new error classes. Curating them where the class is defined removes the drift entirely.

**Surfaced by.** `pipelex-api` Phase 0 review amendment A4.

---

### 2. `PipelexError.type_uri: ClassVar[str | None]`

**Where:** `pipelex/base_exceptions.py:114` (same place as item 1).

**What.** Let `PipelexError` subclasses optionally declare their RFC 7807 `type` URI. Default to `None` → downstream consumers auto-derive `<base>/<kebab-case classname>` from a pipelex-config-provided base URI (default: `https://pipelex.dev/errors/`).

```python
class PipelexError(Exception):
    type_uri: ClassVar[str | None] = None

class EnvVarNotFoundError(PipelexError):
    type_uri = "https://pipelex.dev/errors/env-var-not-found"
```

**Why.** The API today would hardcode `https://pipelex.dev/errors/` as the namespace in `api/error_uri.py`. If pipelex ever moves the docs anchor (renamed domain, restructured docs site, per-class custom anchors), the API has to be updated in lockstep. Owning the URI on the class itself keeps the public-facing identifier and the class definition together, where they belong.

**Surfaced by.** `pipelex-api` Phase 0 design + amendment A4.

---

### 3. First-class `request_id` on workflow input

**Where:** `pipelex/pipeline/pipeline_run_setup.py` (where `pipeline_run_id` is established) and the workflow argument shape consumed by `pipelex/temporal/tprl_pipe/temporal_pipe_run.py:make_temporal_pipe_run`.

**What.** Add a `request_id: str | None` field to whatever pipelex passes as the workflow/activity argument. The worker initializes its logger context from it. Pipelex consumers that drive Temporal (the API, the CLI when it runs async, future SDKs) pass an opaque correlation id; consumers that don't care pass `None`.

```python
@dataclass
class PipeJob:
    ...
    request_id: str | None = None  # NEW — caller-supplied correlation id
```

Worker-side, the logger picks it up at activity entry so every log line emitted during the workflow carries it.

**Why.** The API generates an `X-Request-ID` per inbound HTTP request (Phase 0 of the API plan). For sync `/pipeline/execute`, the request id correlates the API log, pipelex internal logs, and worker logs because they run in the same process. For async `/pipeline/start`, the workflow runs on a different process — without first-class plumbing through Temporal, worker logs are correlated only by `pipeline_run_id`.

Today's workaround (currently in API Phase 4b) is to piggyback on `webhook.payload["request_id"]` — the free-form extras dict on `WebhookTarget` (`pipelex/pipe_run/delivery_assignment.py:16`). That works for the webhook *delivery* log line, but does nothing for the activity's own logs *between* dispatch and delivery — exactly the place operators most need correlation when something goes wrong mid-run.

**Surfaced by.** `track-observability.md` "Request correlation" section.

---

## Stage 2 — Rendering primitives

### 4. `ErrorReport.to_strict_dict()` — disclosure-mode redaction upstream

**Where:** `pipelex/base_exceptions.py:71` (next to `ErrorReport.to_dict()`).

**What.** Add a method (or parameterize `to_dict`) that returns the redacted form for restricted disclosure contexts:

```python
class DisclosureMode(StrEnum):
    VERBOSE = "verbose"
    STRICT = "strict"

@dataclass(frozen=True, ...)
class ErrorReport:
    ...
    def to_strict_dict(self) -> dict[str, Any]:
        """Like to_dict() but with CONFIG/RUNTIME disclosure redacted.

        INPUT-domain errors: returned unchanged. The caller can fix them.
        CONFIG/RUNTIME-domain errors: `message` replaced with a fixed
        string; `user_action`, `provider`, `model`, `provider_metadata`
        dropped; `error_category`, `retryable`, `error_type`, `error_domain`
        retained so consumers can still classify.
        """
        ...
```

**Why.** The architecture doc states **"Don't redefine the mapping"** ([architecture.md](architecture.md) cross-cutting principles). Strict-mode redaction IS the kind of presentational logic that should live where the error model lives — for the same reason `http_status` is on `ErrorReport` and `error_domain_to_http_status` is in pipelex.

Today only the API has a need for this (hosted multi-tenant deployments set `ERROR_DISCLOSURE=strict`). But the moment a second consumer wants the same — the human CLI gains a `--share-error` mode that sanitizes before clipboard, the agent CLI emits errors to a chat surface that may leak, a hosted SDK redacts before forwarding to a user-facing app — the logic gets duplicated, and the two copies will drift.

Owning the rule in pipelex means every consumer gets the same redaction behavior automatically.

**Surfaced by.** `track-response-schema.md` "strict mode, in detail" section + API Phase 1 review note.

---

## Stage 3 — Async error pipe

### 5. `DeliveryExecutor.execute(...)` accepts an `error_report` parameter

**Where:** `pipelex/pipe_run/delivery_executor.py:38-54` (the `execute` method) and `pipelex/pipe_run/delivery_executor.py:238-267` (`_notify_webhook`).

**What.** Extend `DeliveryExecutor.execute(...)` to accept an optional `error_report: ErrorReport | None = None`. When `status == FAILED` and `error_report is not None`, include `error: <error_report.to_dict()>` in the webhook payload. Existing callers passing `None` see unchanged behavior on success.

```python
async def execute(
    self,
    pipe_output: PipeOutput | None,
    user_id: str,
    pipeline_run_id: str,
    delivery_assignment: DeliveryAssignment,
    status: DeliveryStatus,
    error_report: ErrorReport | None = None,  # NEW
) -> None:
    ...
    for webhook in delivery_assignment.webhooks:
        await self._notify_webhook(
            pipeline_run_id, status, result_url, webhook,
            error_report=error_report,  # NEW
        )
```

And `_notify_webhook` adds:

```python
if status == DeliveryStatus.FAILED and error_report is not None:
    payload["error"] = error_report.to_dict()
```

**Recovery responsibility.** `DeliveryExecutor` itself does **not** call `recover_error_report(...)`. The caller — the worker/observer that catches the failing workflow — runs the recovery primitive once and passes the result. Rationale: keeps `DeliveryExecutor` oblivious to `__cause__`-walking, and there is exactly one place that needs to do recovery (the boundary that catches the Temporal failure).

**Unrecoverable case.** When the caller's `recover_error_report(exc)` returns `None` (malformed details, version skew), the caller hand-authors an `ErrorReport` with `error_type="WorkflowFailureUnrecoverable"`, `error_domain="runtime"`, `retryable=False`, and a generic message, and passes that. Same code path, never silent.

**Why.** Without this, `pipelex-api`'s Phase 4 is reduced to "the webhook tells you it FAILED, good luck." The async error pipe is lossy — every classification field (`error_type`, `error_category`, `retryable`, `user_action`, `provider_metadata`) is dropped at the boundary even though pipelex has it in hand. That is the contract that exists today. Phase 4 cannot deliver its promised improvement without this change.

This is **the most important item in the list.** The rest are quality-of-life upgrades that remove duplication or polish the contract. This one is the difference between "the webhook is useful" and "the webhook is a notification with no content."

**Surfaced by.** `track-temporal-recovery.md` and API Phase 4 review amendment A3.

---

## Stage 4 — DX polish

### 6. `ErrorReport.to_problem_document(...)` — optional rendering helper

**Where:** `pipelex/base_exceptions.py` (next to `to_dict()` and `to_strict_dict()` from item 4).

**What.** A thin method that builds the RFC 7807 problem document directly from an `ErrorReport`:

```python
def to_problem_document(
    self,
    *,
    instance: str | None = None,
    request_id: str | None = None,
    disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE,
) -> dict[str, Any]:
    """Return an RFC 7807 problem document built from this report.

    Standard fields (type, title, status, detail, instance) derive from
    the report's classification (using PipelexError.title and .type_uri
    when present on the originating class; humanize fallback otherwise).
    ErrorReport fields ride as RFC 7807 extension members. Strict mode
    is delegated to to_strict_dict.
    """
```

**Why.** Currently the `pipelex-api` Phase 4 decision is: webhook carries raw `ErrorReport` dict (the "consumer renders if needed" path), sync HTTP response renders to RFC 7807 (because HTTP wants it). That decision is correct for today's consumers — a queue / log shipper / batch processor receiving the webhook does not benefit from an envelope.

But the moment a future use case wants "RFC 7807 everywhere" (e.g. a partner integration that consumes both sync and async via one schema, a regulatory requirement to emit `application/problem+json` over both transports), the rendering function needs to be callable from `pipelex/pipe_run/delivery_executor.py`. Today it cannot — the rendering lives in `pipelex-api`, which pipelex does not import.

Landing this method in pipelex now makes "flip to RFC 7807 in webhooks" a one-line change later. The API consumes `to_problem_document(...)` from Phase 1 instead of building its own dict.

**Why this is Stage 4, not Stage 2.** The API's Phase 1 builder needs ~30 lines anyway (to set `Content-Type`, headers, etc.) — the dict-building part is the easy half. We can land items 1, 2, 4 (the inputs to `to_problem_document`) and have the API build its own dict for now. Moving the dict-building upstream is purely about future-flexibility, not about removing today's duplication.

**Surfaced by.** API Phase 4b render-decision discussion.

---

### 7. Per-class `type` URI doc pages

**Where:** pipelex's docs site (`pipelex/docs/...`).

**What.** Generate one stub doc page per `PipelexError` subclass, anchored at the URI declared by `PipelexError.type_uri` (item 2) or the auto-derived default. Each page carries the class name, the title, the domain, the typical `user_action`, links to the parent class doc, and a back-link to the schema page.

A small Sphinx / mkdocs plugin walks the `PipelexError` hierarchy at build time and emits one page per class. Authors override per-class content where it adds value; the default rendered content is fine for most classes.

**Why.** `pipelex-api`'s Phase 5 ships a single generic schema page at `https://pipelex.dev/errors/`. Per-class URIs are stable identifiers but resolve to the schema page until each class has its own. Clients pattern-matching on `type` URIs see broken anchors when they click through to investigate.

Auto-generated stubs make this a zero-maintenance fix — the docs grow as the class hierarchy grows, no manual sync.

**Why this is Stage 4.** Pure docs/DX. No code dependency on the API plan. Pairs naturally with API Phase 5 (where the API publishes its own error-contract docs) but does not block any code work.

**Surfaced by.** API Phase 5 implementation plan + `track-response-schema.md` "type URI namespace" section.

---

## Stage 5 — Future-facing

### 8. `query_pipeline_state(pipeline_run_id)` — sync status-query primitive

**Where:** new in pipelex's Temporal layer (somewhere near `pipelex/temporal/tprl/workflow_caller.py`).

**What.** Expose a pipelex-level function:

```python
async def query_pipeline_state(pipeline_run_id: str) -> PipelineState:
    """Return the current state of a previously-dispatched pipeline run.

    Reads Temporal's workflow history. Returns a structured state object
    that carries enough information for a status response:
      - pending: started_at
      - completed: result_url, completed_at
      - failed: recovered ErrorReport (or None if unrecoverable), failed_at

    The recovery primitive is called internally on the failed branch so
    callers don't need to know about `recover_error_report(...)`. Returns
    a typed state, not an exception.
    """
```

**Why.** `track-temporal-recovery.md` names a future `GET /api/v1/pipeline/{run_id}` endpoint and pins its response shape ("RFC 7807 problem document under `error` for FAILED state, mirroring the webhook"). The endpoint is out of scope for the API plan, but it will become useful the moment a client wants to poll instead of waiting for a webhook (no public endpoint to receive a webhook, firewalled environment, retry-after-restart, etc.).

The blocking question for that endpoint is: how does the API query the state of a Temporal workflow it dispatched earlier, possibly from a different process / different deployment / different replica? Today there is no clean answer. Landing this primitive in pipelex means every consumer (API, CLI, agent CLI, future SDKs) can offer status polling without each rolling its own Temporal-query code.

**Why this is Stage 5.** Not blocking the current API work. The webhook path exists and improves significantly via item 5. The status-query is a different use case (polling, not push) that no current consumer needs yet. But the primitive is small and clean, and landing it now means it's available when the first consumer asks.

**Surfaced by.** `track-temporal-recovery.md` "Synchronous status endpoint (future)" section.

---

## Stage 6 — Security tightening

### 9. `X-Completion-Signature` covers the full webhook payload

**Where:** `api/routes/pipelex/pipeline.py:44-56` (the `_completion_signature` helper) and `pipelex/pipe_run/delivery_executor.py:238-267` (the webhook POST).

**What.** The current HMAC-SHA256 signature in `X-Completion-Signature` covers only `pipeline_run_id`. Sign the full payload instead.

```
sig = HMAC-SHA256(secret, request_body_bytes)
header: X-Completion-Signature: sha256=<hex>
```

The signature is computed against the exact serialized body. Receivers verify by re-hashing the body they got.

**Why.** Pre-existing weakness — a man-in-the-middle who can rewrite the body but not regenerate the signature can change `status`, `result_url`, or (after item 5 lands) the entire `error` payload, and the signature still verifies. Adding rich `error` content to the payload makes the tamper surface meaningfully larger than it was, which is why this is being addressed now even though it's an independent track.

The change spans both repos: `pipelex-api` updates `_completion_signature` to take the body bytes; pipelex's `_notify_webhook` computes the signature on the serialized body before POST. Cross-repo, but a small total diff.

**Why this is Stage 6.** Independent of the error model. Can land anytime — before, during, or after the rest of this list. Listed last because the work itself is straightforward and the cross-repo coordination is the only friction.

**Surfaced by.** `track-temporal-recovery.md` "Webhook signing and integrity" section.

---

## What NOT to push upstream

Things that look like they belong in pipelex but actually stay API-side.

- **The `api/errors.py` 4xx helpers.** `raise_validation_error`, `raise_bad_request`, `raise_forbidden`, `raise_unauthenticated`, `raise_payload_too_large`, `raise_internal_server_error`. FastAPI-specific. They emit RFC 7807 problem documents that pipelex itself never sees. Pushing them upstream would couple pipelex to FastAPI, which the project explicitly avoids ("the library itself stays HTTP-agnostic — no web-framework import lives here, only the mapping table" — `base_exceptions.py:23`).
- **The `api/error_types.py` `ErrorType` enum.** Static API-owned error_type values for API-authored validation errors. Stays API-owned. Pipelex's `error_type` field is open-ended on purpose so the class name can be the identifier.
- **Auth errors (`api/security.py`).** 401/403 are HTTP-layer concerns, not pipelex domain errors. Pipelex's error hierarchy does not (and should not) contain "invalid JWT signature."
- **CORS, request body size limits, request id middleware, the request-id contextvar.** All API/HTTP concerns.
- **Default disclosure mode.** Whether to default to verbose or strict is a deployment choice. Pipelex provides the redaction primitive (item 4); the consumer picks the default.

---

## Tracking

| # | Item | Stage | pipelex file | Status | PR |
|---|---|---|---|---|---|
| 1 | `PipelexError.title` class attribute | 1 | `base_exceptions.py:114` | Not started | — |
| 2 | `PipelexError.type_uri` class attribute | 1 | `base_exceptions.py:114` | Not started | — |
| 3 | First-class `request_id` on workflow input | 1 | `pipeline_run_setup.py`, `temporal_pipe_run.py` | Not started | — |
| 4 | `ErrorReport.to_strict_dict()` | 2 | `base_exceptions.py:71` | Not started | — |
| 5 | `DeliveryExecutor.execute(error_report=...)` | 3 | `pipe_run/delivery_executor.py:38` | Not started | — |
| 6 | `ErrorReport.to_problem_document()` | 4 | `base_exceptions.py` | Not started | — |
| 7 | Per-class `type` URI doc pages | 4 | `docs/` | Not started | — |
| 8 | `query_pipeline_state(...)` | 5 | `temporal/tprl/workflow_caller.py` (new) | Not started | — |
| 9 | Webhook signature covers full payload | 6 | `pipe_run/delivery_executor.py:_notify_webhook` + `api/routes/pipelex/pipeline.py:_completion_signature` | Not started | — |

Update the Status / PR columns as items land. When all of Stage 1-3 are landed, the `pipelex-api` plan unblocks fully — Phase 0 consumes items 1+2 directly, Phase 1 consumes item 4 directly, and Phase 4 consumes item 5 directly.
