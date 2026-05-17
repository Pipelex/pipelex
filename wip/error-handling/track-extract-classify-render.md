# Track — Extract / Classify / Render Decomposition

## What this track is

Today every inference worker performs three logically separate steps inline inside its `except` blocks: (1) **Extract** structured metadata from the SDK exception (status code, request id, retry-after, error code, body), (2) **Classify** the error into an `InferenceErrorCategory` + `UserActionKind`, and (3) **Render** a `CogtError` subclass with a human-readable message and the categorization attached. The three steps are tangled together, and every new provider duplicates the entire pipeline.

This track proposes decomposing the pipeline so that only the **Extract** step is per-provider. **Classify** and **Render** become provider-agnostic and share a single implementation across all 18+ workers.

This track is **proposed but not started.** It is the natural next step after the worker-classification sweep, which has landed ([archive-worker-classification-sweep.md](archive-worker-classification-sweep.md)): now that every worker uniformly attaches `ProviderErrorMetadata` and a structured `UserAction`, the duplication across workers is the dominant complexity, and decomposition is the obvious cleanup.

## Current state

After the worker-classification sweep, a worker looks like this:

```python
except RateLimitError as exc:
    metadata = extract_openai_metadata(exc)
    if is_quota_exhaustion_openai(metadata.message):
        msg = f"OpenAI quota exhausted for model '{self.inference_model.desc}': {exc}"
        raise LLMCompletionError(
            message=msg,
            error_category=InferenceErrorCategory.CAPACITY,
            user_action=UserAction(
                kind=UserActionKind.CHECK_BILLING,
                detail="Your OpenAI account has exceeded its quota — check your billing dashboard",
            ),
            provider_metadata=metadata,
        ) from exc
    msg = f"Rate limited by OpenAI for model '{self.inference_model.desc}': {exc}"
    raise LLMCompletionError(
        message=msg,
        error_category=InferenceErrorCategory.TRANSIENT,
        user_action=UserAction(
            kind=UserActionKind.WAIT_AND_RETRY,
            detail=f"Rate limited by OpenAI — will retry after {metadata.retry_after_seconds}s",
        ),
        provider_metadata=metadata,
    ) from exc
```

This same shape repeats across:

- 6 LLM workers
- 7 img-gen workers
- 5 extract workers
- 2 search workers
- Gateway variants

Each worker duplicates: the discriminator invocation, the message construction, the `UserAction` composition, the `from exc` chaining, the `error_category` selection, and the `provider_metadata` attachment. A new provider (or a new SDK exception type) requires modifying all three steps in lockstep.

Discriminator helpers like `is_quota_exhaustion_openai` (in `pipelex/cogt/inference/error_classification.py`) are extraction primitives but they live alongside classification logic, and they're called from inside each worker rather than from a central Classify step.

## Open gaps

### Duplicated classification logic across providers

Every worker hard-codes the mapping `(SDK exception, status_code, message_pattern) → (category, user_action_kind)`. Adding a new category (e.g. splitting `TRANSIENT` into `RATE_LIMITED` and `SERVER_ERROR`) requires touching every worker.

### Coupling between extraction and rendering

The message string is composed inline using both the SDK exception and the categorization result. There is no clean separation between "what happened" (factual metadata) and "what the user should be told" (presentation). Localization, structured logging, and provider-blind testing all suffer.

### New SDK exception types are silent gaps

If a provider adds a new SDK exception type, today's categorization helper returns without raising and falls through to `UNKNOWN`. The Extract layer would centralize "did we see something we don't recognize" detection in one place — and emit a metric the moment the unknown class appears, instead of waiting for a categorization audit.

### Cross-provider parity testing is expensive

Testing that "every provider classifies HTTP 429 as TRANSIENT" requires a per-provider test fixture today. With decomposition, the Classify step becomes a pure function `(envelope) → (category, user_action_kind)` that can be tested provider-blind against synthetic envelopes — provider parity reduces to "every Extract function produces a well-formed envelope."

## Proposed design

### Three layers

**1. Extract** (per-provider, small):

```python
def extract_anthropic_metadata(exc: anthropic.APIError) -> SDKErrorEnvelope:
    response = getattr(exc, "response", None)
    return SDKErrorEnvelope(
        provider=ProviderName.ANTHROPIC,
        sdk_exception_type=type(exc).__name__,
        status_code=getattr(response, "status_code", None),
        request_id=getattr(exc, "request_id", None),
        retry_after_seconds=_parse_retry_after(response),
        provider_error_code=getattr(exc, "type", None),
        message=str(exc),
        body=getattr(exc, "body", None),
    )
```

Each provider has exactly one Extract function. Adding a provider = adding one function. The function is the only place provider-specific attribute access lives.

**2. Classify** (shared, pure):

```python
def classify_inference_error(envelope: SDKErrorEnvelope) -> ClassificationResult:
    if envelope.status_code == 429:
        if envelope.is_quota_exhaustion:
            return ClassificationResult(
                category=InferenceErrorCategory.CAPACITY,
                user_action_kind=UserActionKind.CHECK_BILLING,
            )
        return ClassificationResult(
            category=InferenceErrorCategory.TRANSIENT,
            user_action_kind=UserActionKind.WAIT_AND_RETRY,
        )
    if envelope.status_code in (502, 503, 504):
        return ClassificationResult(InferenceErrorCategory.TRANSIENT, UserActionKind.WAIT_AND_RETRY)
    if envelope.status_code in (401, 403):
        return ClassificationResult(InferenceErrorCategory.CONFIGURATION, UserActionKind.CHECK_CREDENTIALS)
    if envelope.is_content_policy_violation:
        return ClassificationResult(InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT)
    if envelope.status_code == 404:
        return ClassificationResult(InferenceErrorCategory.CONFIGURATION, UserActionKind.CHANGE_MODEL)
    ...
    return ClassificationResult(InferenceErrorCategory.UNKNOWN, UserActionKind.CONTACT_SUPPORT)
```

One function. Provider-agnostic. Tests are synthetic-envelope-driven and don't need any SDK installed.

**3. Render** (shared, small):

```python
def render_inference_error(
    envelope: SDKErrorEnvelope,
    classification: ClassificationResult,
    model_desc: str,
    error_type: type[CogtError],
) -> CogtError:
    detail = _default_detail(envelope, classification)
    msg = _format_message(envelope, model_desc, classification.category)
    return error_type(
        message=msg,
        error_category=classification.category,
        user_action=UserAction(kind=classification.user_action_kind, detail=detail),
        provider_metadata=envelope,
    )
```

### Worker shape after decomposition

```python
except anthropic.APIError as exc:
    envelope = extract_anthropic_metadata(exc)
    classification = classify_inference_error(envelope)
    raise render_inference_error(
        envelope, classification, self.inference_model.desc, LLMCompletionError,
    ) from exc
```

Three lines per catch. Worker code shrinks dramatically — most existing 30-line catch bodies become a single delegation.

## Tradeoffs

**For:**

- New providers and new SDK exception types only need an Extract function update.
- Classify is one provider-agnostic function — easier to test exhaustively, easier to reason about.
- Cross-provider parity tests become trivial (synthesize an envelope, assert classification).
- Localization and CLI rendering changes touch one Render function, not 18+.
- Tests of Classify are provider-blind — they run without any SDK installed (faster, fewer cross-package imports).

**Against:**

- Real refactor — touches every worker. Should land in one coordinated sweep, not piecemeal.
- Some provider-specific nuance (Anthropic's `type` vs. OpenAI's `code` vs. Google's nested error structure) must be encoded in either the envelope schema OR the Classify function. Risk: the envelope becomes a kitchen sink. Mitigation: keep envelope schema flat and provider-blind; put any "is this a quota error?" smarts into computed `@property` accessors that read `status_code` + `message` + `provider`.
- Today's per-worker tests test the full pipeline end-to-end; after decomposition, per-worker tests only verify the Extract function, and a new test suite covers Classify+Render. More test files; each is smaller and faster.
- The Anthropic worker is currently the "reference" implementation. After this refactor, the reference is split across `extract_anthropic_metadata`, the shared Classify helper, and the shared Render helper. The Anthropic worker file shrinks dramatically. Some readers find that disorienting at first.

## Risks and gotchas

### `InferenceErrorCategory` granularity

Decomposition exposes the limitations of today's categories. May want to split `TRANSIENT` → `RATE_LIMITED` / `SERVER_ERROR` / `NETWORK` at the same time. Mitigation: do the refactor with existing categories first; split categories in a follow-up if needed. The Classify function makes the split trivial later.

### Provider-specific user actions

Some providers have unique recovery actions (e.g. AWS regional capacity → "try another region"). The `UserActionKind` enum needs to be expressive enough OR the `detail` field carries the provider-specific advice. Mitigation: start with the existing `UserActionKind` set; add new kinds only when a provider-specific case can't be expressed via detail.

### Streaming errors

Currently no worker streams. If streaming is added, the envelope schema must handle partial-response errors (partial body, error mid-stream, resume index). Mitigation: out of scope until a streaming worker materializes.

### `InstructorRetryException` integration

The unwrap helper from track-worker-classification stays — it returns the SDK exception, which then goes through `extract_<provider>_metadata`. The decomposition assumes the helper has already unwrapped. The fallback case (unrecognized underlying like `pydantic.ValidationError`) becomes "envelope with `sdk_exception_type='ValidationError'` and `provider=<the provider>`, classify → UNKNOWN" — clean.

### Envelope field optionality

Some providers don't always populate every field (e.g. Google's `genai_errors.ClientError` doesn't always carry a `request_id`). The envelope must be permissive (Optional fields) but the Classify function must not assume optionals are present without checks.

## Followups

### 1. Define the schemas

- `SDKErrorEnvelope` (Pydantic `BaseModel`):
  - `provider: ProviderName`
  - `sdk_exception_type: str`
  - `status_code: int | None`
  - `request_id: str | None`
  - `retry_after_seconds: float | None`
  - `provider_error_code: str | None`
  - `message: str`
  - `body: Any | None`
  - Computed `@property`: `is_quota_exhaustion`, `is_content_policy_violation`, `is_network_error`
- `ClassificationResult` (Pydantic `BaseModel`): `category: InferenceErrorCategory`, `user_action_kind: UserActionKind`
- `ProviderName` (`StrEnum` from `pipelex.types`): one value per provider plugin (`ANTHROPIC`, `OPENAI`, `MISTRAL`, `GOOGLE`, `BEDROCK`, `AZURE`, `FAL`, `HUGGINGFACE`, `DOCLING`, `LINKUP`, `GATEWAY`, ...)

`SDKErrorEnvelope` is likely identical to the existing `ProviderErrorMetadata` (`pipelex/cogt/inference/error_classification.py`) — rename rather than reintroduce.

### 2. Write the Classify function first (TDD)

Pure function, easy to test with synthetic envelopes. Build the test suite that captures cross-provider parity rules:

| Envelope shape | Expected category | Expected user_action_kind |
|---|---|---|
| status=429, is_quota_exhaustion=False | TRANSIENT | WAIT_AND_RETRY |
| status=429, is_quota_exhaustion=True | CAPACITY | CHECK_BILLING |
| status=503 | TRANSIENT | WAIT_AND_RETRY |
| status=401 | CONFIGURATION | CHECK_CREDENTIALS |
| status=400, is_content_policy_violation=True | CONTENT | CHANGE_INPUT |
| status=400, is_content_policy_violation=False | CONTENT | (default) |
| status=404 | CONFIGURATION | CHANGE_MODEL |
| status=None, sdk_exception_type="ConnectionError" | TRANSIENT | WAIT_AND_RETRY |
| status=None, sdk_exception_type="TimeoutError" | TRANSIENT | WAIT_AND_RETRY |
| status=None, sdk_exception_type="ValidationError" | CONTENT | (default) |
| Everything else | UNKNOWN | CONTACT_SUPPORT |

### 3. Write the Render function

Mostly mechanical. Tests use synthetic envelopes + classifications.

### 4. Migrate workers one at a time

Each worker gets:

- A new `extract_<provider>_metadata` function in `pipelex/cogt/inference/error_classification.py` (or co-located with the provider plugin if cleaner)
- A single tuple-catch in the worker that delegates to extract → classify → render
- Existing per-worker tests rewritten to use the new shape — most categorization assertions move to the Classify test suite

The per-worker test surface SHRINKS (the worker now does less). The Classify and Render test surface is paid once, not per provider. Net win.

### 5. Delete redundant discriminator helpers

`is_quota_exhaustion_<provider>` becomes either:

- A computed `@property` on `SDKErrorEnvelope` (preferred — provider + status_code + message decide)
- A private helper called from inside Classify

Either way, the per-worker callers go away.

### 6. Cross-provider parity meta-test

Once all workers are migrated, write a meta-test that exercises every (provider, error-category) pair: given each provider's Extract function and a synthetic exception per category, verify the rendered error has the expected category, user_action_kind, and a populated request_id. Catches "we added a provider and forgot to wire it up" regressions.

## Prerequisites — all met

This refactor depended on the worker-classification sweep landing first. Those prerequisites are all in place:

- `InferenceErrorCategory.UNKNOWN` exists (`pipelex/cogt/exceptions.py`).
- `ProviderErrorMetadata` exists as a Pydantic model with the right field shape — likely renamed to `SDKErrorEnvelope` when this refactor starts (`pipelex/cogt/inference/error_classification.py`).
- `UserAction` is structured (`UserActionKind` enum + `detail` string).
- The `instructor`-unwrap fix is landed on every LLM worker, so each has a clean post-unwrap call site to refactor.

The refactor can start whenever it is prioritized; nothing blocks it.

**Estimated effort:** 2–3 days of focused work — mostly mechanical migration after the schemas are right.

## Related tracks

- [track-worker-classification.md](track-worker-classification.md) — the current per-worker classification. This track is the next step once classification is uniform across providers.
- [track-metadata-model.md](track-metadata-model.md) — the data contract this track restructures. `ProviderErrorMetadata` becomes `SDKErrorEnvelope`.
- [track-retry-and-resilience.md](track-retry-and-resilience.md) — benefits from the structured `retry_after_seconds` and uniform category-to-retry policy that decomposition makes obvious.
- [track-testing.md](track-testing.md) — cross-provider parity tests become much cheaper with provider-blind Classify tests.
- [track-cli-delivery.md](track-cli-delivery.md) — the Render layer becomes the single place to update human-facing message formatting.
