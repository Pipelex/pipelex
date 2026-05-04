# Worker Error Handling Review

> Review date: 2026-04-05  
> Scope: All inference workers (LLM, Extract, ImgGen, Search) across all SDK plugins

---

## Tier Ranking: Best to Worst

### Tier 1 — Gold Standard

| Worker | Provider | Why |
|--------|----------|-----|
| `openai_responses_llm_worker.py` | OpenAI Responses API | Catches all 4 SDK exception types individually; uses specialized `LLMModelNotFoundError` with `model_handle`; nested instructor error handling; includes model descriptor in every message |
| `openai_completions_llm_worker.py` | OpenAI Completions API | Same 4-exception pattern; response structure validation after call; instructor retry errors caught separately |
| `anthropic_llm_worker.py` | Anthropic | Catches `BadRequestError`, `APIConnectionError`, `AuthenticationError`; uses specialized `AnthropicCredentialsError`; constructor validates `max_tokens`; response content validated block-by-block |
| `gateway_extract_worker.py` | Gateway (Portkey) | Catches `portkey_exceptions.APIError`; tenacity retry with custom `_is_retryable_portkey_error` predicate; logs attempt number + wait duration; error summary via `GatewayFactory` |
| `gateway_search_worker.py` | Gateway (Portkey) | Same retry pattern; content extraction wrapped in `(KeyError, IndexError, TypeError)` catch; null-response guard after retries |

### Tier 2 — Partial Coverage

| Worker | Provider | Gap |
|--------|----------|-----|
| `openai_completions_img_gen_worker.py` | OpenAI Completions (images) | Catches `NotFoundError`, `APIConnectionError`, `BadRequestError` but **missing `AuthenticationError`**; good response parsing with multiple fallback strategies |
| `gateway_img_gen_worker.py` | Gateway (images) | Catches `portkey_exceptions.APIError`; complex multi-schema response parsing with accumulated `parsing_errors`; FAL polling fallback. But **no retry logic** unlike gateway extract/search |
| `openai_img_gen_worker.py` | OpenAI Images | Good response validation (checks data, format, size, base64). But **no SDK exception handling at all** — relies on raw exceptions bubbling up |
| `bedrock_llm_worker.py` | AWS Bedrock | Constructor validates `max_tokens`; capability checks for reasoning params. But **no try/except around API calls** |
| `mistral_llm_worker.py` | Mistral | Constructor validates `max_tokens`; detailed response content type handling (TextChunk/ThinkChunk). But **no SDK exception handling** |

### Tier 3 — Minimal or No Error Handling

| Worker | Provider | Issue |
|--------|----------|-------|
| `google_llm_worker.py` | Google Gemini | **No SDK exception handling**; delegates response extraction to `GoogleFactory`; has its own `GoogleLLMWorkerError` but only for type mismatches |
| `google_img_gen_worker.py` | Google Gemini Images | **No SDK exception handling**; response validation is good (checks candidates, content parts, mime type) but API errors go uncaught |
| `azure_img_gen_worker.py` | Azure REST (httpx) | Uses `response.raise_for_status()` which throws raw `httpx.HTTPStatusError` — **no wrapping in domain exceptions** |
| `mistral_extract_worker.py` | Mistral OCR | **No error handling at all** — delegates entirely to SDK |
| `fal_img_gen_worker.py` | FAL | **No error handling** — logs FAL events but doesn't catch failures |
| `huggingface_img_gen_worker.py` | HuggingFace | **No error handling** — trusts SDK entirely |
| `docling_extract_worker.py` | Docling (local) | Only has `finally` for temp file cleanup — **no error handling** on conversion |
| `pypdfium2_worker.py` | pypdfium2 (local) | Input validation only — **no error handling** on PDF operations |
| `linkup_extract_worker.py` | Linkup | **No error handling** |
| `linkup_search_worker.py` | Linkup | **No error handling** |

---

## What the Best Workers Do Right

These patterns from Tier 1 workers should be the standard:

### 1. Catch specific SDK exceptions individually

```python
except NotFoundError as exc:
    msg = f"Model or deployment '{self.inference_model.model_id}' not found: {exc}"
    raise LLMModelNotFoundError(message=msg, model_handle=self.inference_model.name) from exc
except APIConnectionError as exc:
    msg = f"API connection error: {exc}"
    raise LLMCompletionError(msg) from exc
except BadRequestError as exc:
    msg = f"Bad request with model {self.inference_model.desc}:\n{exc}"
    raise LLMCompletionError(msg) from exc
except AuthenticationError as exc:
    msg = f"Authentication error: {exc}"
    raise CredentialsError(msg) from exc
```

**Why this matters for agents:** An agent skill iterating on a failing method needs to know *why* it failed. "Model not found" means the `.mthds` file references a wrong model — the agent can suggest alternatives. "Auth error" means the user needs to fix their API key — the agent should stop retrying and ask the human. "Bad request" might mean the prompt is too long or uses unsupported features — the agent can try reformulating.

### 2. Use specialized exception types with structured fields

The `LLMModelNotFoundError` carries `model_handle`, `ModelChoiceNotFoundError` carries `available_options` and `suggestions`. This lets upstream code (pipe operators, CLI, agent skills) make smart decisions:

```python
except ModelChoiceNotFoundError as exc:
    # Agent can show: "Model 'gpt-5-turbo' not found. Did you mean: gpt-4-turbo, gpt-4o?"
    suggest_alternatives(exc.suggestions, exc.available_options)
```

### 3. Validate response structure after the call

Even when the API call succeeds, the response may be malformed. Tier 1 workers check:
- Response is not None
- Expected fields exist (choices, content, data)
- Content is not empty
- Types match expectations

### 4. Retry with discrimination (gateway workers)

```python
def _is_retryable_portkey_error(self, exc: BaseException) -> bool:
    if isinstance(exc, portkey_exceptions.NotFoundError):
        msg = str(exc).lower()
        return "specified deployment could not be found" in msg
    return False
```

Not all errors deserve retries. Auth errors and bad requests should fail fast. Transient deployment errors and rate limits should retry with backoff.

### 5. Include model descriptor in every error message

Every error message includes `self.inference_model.desc` or `self.inference_model.model_id`. This is critical when a pipeline uses multiple models — the user needs to know *which* model failed.

---

## What's Missing Across the Board

### A. Rate limit handling — nowhere

No worker catches rate limit errors (`RateLimitError` in OpenAI, `429` status in others). This is the most common transient error in production. The SDK's built-in retry may handle some cases, but:
- We don't surface "you're being rate limited" to the user
- We don't have backoff control
- Agents can't distinguish "wait and retry" from "permanently broken"

### B. Timeout handling — nowhere

No worker catches timeout errors. Long-running generations (especially image gen) can time out. Users see a generic connection error instead of "generation timed out, try again or use a faster model."

### C. Content policy / safety filter errors — nowhere

OpenAI and Anthropic can reject requests due to content policy. These come as `BadRequestError` with specific error codes. Currently they're lumped in with all other bad requests. Users get "bad request" when they should get "content was flagged by safety filters."

### D. Quota / billing errors — nowhere

Distinct from rate limits. "You've exceeded your monthly quota" or "your plan doesn't include this model" should be clearly surfaced, not buried in a generic auth or bad request error.

**Detection strategy:** Rate limit (429) and quota exhaustion (429) often share the same HTTP status. Must inspect the error body to distinguish:

| Provider | Rate limit (TRANSIENT) | Quota exhausted (CAPACITY) |
|----------|----------------------|---------------------------|
| OpenAI | `RateLimitError` (429) generic | `RateLimitError` with `"insufficient_quota"` or `"exceeded your current quota"` in message; `AuthenticationError` with `"insufficient_quota"` |
| Anthropic | `RateLimitError` (429) generic | `RateLimitError` or `PermissionDeniedError` with `"quota"` or `"billing"` in message |
| Google | `ResourceExhausted` generic | `ResourceExhausted` with `"billing"` or `"quota"` in message |
| Mistral | 429 generic | 402 Payment Required; 429 with `"quota"` in message |
| Azure | 429 generic | 429 with `"quota"` or `"billing"` in body; 402 |
| AWS Bedrock | `ThrottlingException` generic | `ServiceQuotaExceededException`; `ThrottlingException` with `"quota"` or `"limit exceeded"` |
| Portkey/Gateway | `APIError` 429 | `APIError` 402; 429 with `"quota"` / `"billing"` / `"insufficient"` |

**Key principle:** Quota exhaustion check must happen **before** the generic rate-limit handler, since both may raise the same exception type. The message body is the discriminator.

### E. No error categorization enum

The codebase has `InferenceBackendCredentialsErrorType` for credential errors, but there's no general `InferenceErrorCategory` enum that classifies errors as:
- `TRANSIENT` (retry-safe: rate limit, timeout, server error)
- `CONFIGURATION` (fix needed: auth, missing model, wrong params)  
- `CONTENT` (user action needed: safety filter, too long, unsupported format)
- `CAPACITY` (wait or upgrade: quota exceeded, model overloaded)

This classification is essential for agent-driven error recovery.

---

## Proposed Action Plan

### Phase 1: Error classification infrastructure

1. **Create `InferenceErrorCategory` enum** with categories: `TRANSIENT`, `CONFIGURATION`, `CONTENT`, `CAPACITY`, `UNKNOWN`

2. **Add `error_category` field to `CogtError`** (or a new `InferenceError` base class) so every inference error self-classifies

3. **Add optional `user_action` field** — a short, plain-English suggestion:
   - "Check your API key for {backend_name}"
   - "Model '{model_handle}' is not available on your plan — try {alternatives}"
   - "Your prompt was flagged by content filters — revise the prompt"
   - "Rate limited — the system will retry automatically"

### Phase 2: Bring all workers to Tier 1

For each worker, add SDK-specific exception handling following the OpenAI Responses pattern. The specific exceptions to catch vary by SDK:

| SDK | Exceptions to catch |
|-----|-------------------|
| OpenAI | `NotFoundError`, `APIConnectionError`, `BadRequestError`, `AuthenticationError`, `RateLimitError`, `APITimeoutError`, `APIStatusError` (catch-all for other HTTP errors) |
| Anthropic | `BadRequestError`, `APIConnectionError`, `AuthenticationError`, `RateLimitError`, `APITimeoutError`, `APIStatusError` |
| Google genai | `google.api_core.exceptions.NotFound`, `google.api_core.exceptions.PermissionDenied`, `google.api_core.exceptions.ResourceExhausted`, `google.api_core.exceptions.InvalidArgument`, `google.api_core.exceptions.ServiceUnavailable`, `google.api_core.exceptions.DeadlineExceeded` |
| Mistral | `mistralai.models.sdkerror.SDKError` and HTTP-based exceptions from their client |
| httpx (Azure) | `httpx.HTTPStatusError` (with status code inspection), `httpx.ConnectError`, `httpx.TimeoutException` |
| FAL | `fal_client.FalClientError` or equivalent |
| HuggingFace | `huggingface_hub.errors.HfHubHTTPError` and subclasses |
| Linkup | Check SDK for specific exceptions |
| Docling | `docling.exceptions.*` or generic conversion errors |

### Phase 3: Content policy detection

For OpenAI and Anthropic specifically, inspect the error body for content policy signals:

```python
except BadRequestError as exc:
    if "content_policy" in str(exc) or "safety" in str(exc).lower():
        msg = f"Content was rejected by {provider}'s safety filters: {exc}"
        raise ContentPolicyError(msg, category=CONTENT) from exc
    msg = f"Bad request with model {self.inference_model.desc}:\n{exc}"
    raise LLMCompletionError(msg, category=CONFIGURATION) from exc
```

Also check `response.choices[0].finish_reason` for `"content_filter"` in OpenAI responses — this is a *successful* API call where the content was filtered in the response, not an exception.

### Phase 4: Retry standardization

Extend the gateway workers' tenacity pattern to all workers that make remote API calls:

- **Retry on:** `TRANSIENT` category errors (rate limit, timeout, 5xx server errors)
- **Fail fast on:** `CONFIGURATION`, `CONTENT`, `CAPACITY` errors
- **Configurable:** max retries, backoff multiplier from worker config
- **Observable:** log each retry with attempt number, wait duration, error category

Consider a shared `@with_inference_retry` decorator or mixin to avoid duplicating retry logic in every worker.

### Phase 5: Agent-friendly error reporting

Add a `to_agent_report()` method on inference errors that returns a structured dict:

```python
{
    "error_category": "CONFIGURATION",
    "provider": "openai",
    "model": "gpt-4o",
    "summary": "Authentication failed for OpenAI API",
    "user_action": "Check that your OPENAI_API_KEY environment variable is set and valid",
    "retryable": False,
    "original_error": "Error code: 401 - Invalid API key provided"
}
```

This allows MTHDS skills to:
- Decide whether to retry or escalate to the human
- Show the user exactly what to fix
- Log structured error data for debugging

---

## Priority Matrix

| Action | Impact | Effort | Priority |
|--------|--------|--------|----------|
| Bring Google, Mistral, FAL, HuggingFace, Docling, Linkup workers to Tier 1 | High — these currently bubble raw SDK errors | Medium | **P0** |
| Add rate limit + timeout handling to OpenAI/Anthropic workers | High — most common production errors | Low | **P0** |
| Create `InferenceErrorCategory` enum | High — enables all downstream improvements | Low | **P1** |
| Add `error_category` to `CogtError` | Medium — structural change | Low | **P1** |
| Content policy detection | Medium — improves UX for flagged content | Low | **P1** |
| Retry standardization across workers | Medium — reduces transient failures | Medium | **P2** |
| `to_agent_report()` for structured error reporting | High for agent workflows | Medium | **P2** |
| Add `user_action` suggestions to all error paths | High UX impact | Medium | **P2** |

---

## Appendix: Current State by Worker

| Worker | SDK Exceptions | Response Validation | Constructor Validation | Retry Logic | Error Category | Model in Msg |
|--------|:-:|:-:|:-:|:-:|:-:|:-:|
| `openai_responses_llm_worker` | 4/4 | yes | no | no | no | yes |
| `openai_completions_llm_worker` | 4/4 | yes | no | no | no | yes |
| `anthropic_llm_worker` | 3/3 | yes | yes | no | no | yes |
| `gateway_extract_worker` | yes | yes | no | yes | no | yes |
| `gateway_search_worker` | yes | yes | no | yes | no | yes |
| `openai_completions_img_gen_worker` | 3/4 | yes | no | no | no | yes |
| `gateway_img_gen_worker` | yes | yes | no | no | no | yes |
| `openai_img_gen_worker` | **no** | yes | no | no | no | partial |
| `bedrock_llm_worker` | **no** | minimal | yes | no | no | yes |
| `mistral_llm_worker` | **no** | yes | yes | no | no | yes |
| `google_llm_worker` | **no** | delegated | no | no | no | yes |
| `google_img_gen_worker` | **no** | yes | no | no | no | yes |
| `azure_img_gen_worker` | raw httpx | yes | no | no | no | partial |
| `mistral_extract_worker` | **no** | **no** | no | no | no | no |
| `fal_img_gen_worker` | **no** | **no** | no | no | no | no |
| `huggingface_img_gen_worker` | **no** | **no** | no | no | no | no |
| `docling_extract_worker` | **no** | **no** | no | no | no | no |
| `pypdfium2_worker` | **no** | input only | no | no | no | no |
| `linkup_extract_worker` | **no** | **no** | no | no | no | no |
| `linkup_search_worker` | **no** | **no** | no | no | no | no |
