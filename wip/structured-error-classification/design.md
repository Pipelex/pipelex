---
status: active
item: L-260927-086ea4
---

# A gateway's model_not_allowed refusal says to change the model

## The bug, verified

The item reports that a run whose model the gateway refuses reaches the user as an unknown runtime failure. Verification on 2026-09-27 found two independent causes. The first has since been fixed by the instructor upgrade (pipelex#1289, merged as `85729dfd3`). The second is what remains of this item.

### Cause 1, fixed: instructor's new retry loop hid the SDK exception

The campaign's failure message was the fallback text of `OpenAICompletionsLLMWorker._gen_object`. That text is produced when `extract_underlying_sdk_exception` cannot find the SDK exception inside an `InstructorRetryException`, and it carries `error_category=UNKNOWN` and no user action. From instructor 1.15.3 on, every `from_*` factory runs through `instructor/v2/core/retry.py`, which raises `InstructorRetryException` from any exception that ends the loop. It records only parse failures in `failed_attempts`, so an API error sits on `__cause__` alone. The recovery only looked in `failed_attempts` and in a tenacity `RetryError`. As a result, every provider error on a structured-output call was reported as unclassified and never retried, on every LLM worker that uses instructor. This was bisected over `httpx.MockTransport`: 1.15.1 raised the SDK exception raw, while 1.15.3, 1.15.4 and 1.17.0 wrapped it.

pipelex#1289 moved the lock to instructor 1.17.0 and the floor to `>=1.17.0,<2.0.0`, and it reordered the recovery to read `__cause__` first, unwrapping a tenacity `RetryError`, with `failed_attempts` as the fallback. That is the order the first draft of this design proposed. It also rewrote `wrap_in_instructor_retry` to build the new shape, and the "`instructor` Unwrap" section of `docs/under-the-hood/error-model.md`.

Re-verified at `85729dfd3`, by driving the real instructor factories over `httpx.MockTransport` with `make_instructor_schema_retrying(max_attempts=3)`, then running the recovery, classify and render:

| Scenario | Recovered | Report |
|---|---|---|
| OpenAI, gateway 412 `model_not_allowed_error` | `APIStatusError` | `configuration` / `config` / 500 / `change_input`: "The provider rejected the request — review the prompt, parameters, and inputs." |
| OpenAI, invalid output then 429 | `RateLimitError` | `transient` / `runtime` / 429 / `wait_and_retry`, retryable |
| OpenAI, re-ask budget spent | `ValidationError` | `content` / `input` / 422 / `change_input` |
| Anthropic, 429 | `RateLimitError` | `transient` / `runtime` / 429 / `wait_and_retry`, retryable |

The hosted plane still runs this bug: `pipelex-server` pins `pipelex==0.68.0`, which was released before `85729dfd3`, and its lock resolves instructor 1.15.4. It gets the fix with the next pipelex release and the pin move that follows, so nothing needs filing.

### Cause 2, open: a 412 lands on the status ladder's generic 4xx arm

Now that the SDK exception is recovered, the 412 is classified. `extract_openai_metadata` reads `provider_error_code = "model_not_allowed_error"` off `exc.type`, but no code map knows that code. So `classify_inference_error` falls through to its unrecognized-4xx arm (`pipelex/cogt/inference/error_classify.py`, the `if status_code >= 400:` branch), which returns `CONFIGURATION` / `CHANGE_INPUT`. The domain is right. The action is wrong: nothing in the prompt, parameters or inputs causes this refusal, and only another model avoids it. A caller branching on `user_action.kind` is sent to edit its inputs.

### Where the refusal comes from

`model_not_allowed_error` is the Portkey gateway's own code, not a model vendor's. Both raise sites are in the middleware the manifold vendors from upstream (`pipelex-manifold/src/middlewares/portkey/utils.ts`). They answer HTTP 412 with `{error: {message: "Model <wire id> is not allowed for this integration", type: "model_not_allowed_error", param: null, code: null}}` in two cases: the integration has `allow_all_models` off and does not list the model, or it lists the model as `archived`.

`pipelex_gateway` points at Portkey's cloud by default (`pipelex/providers/gateway/gateway_factory.py`, `get_endpoint`), where Pipelex configures the integrations. The manifold would raise the same code if one of its integrations turned `allow_all_models` off. So does Portkey's cloud for a user's own workspace reached through the `portkey` backend, which runs on the same OpenAI completions worker and Extract hop and reports the same provider; there the allow-list is the user's own. Either way, the model exists, and the integration that would serve it refuses it for this caller. The caller can pick another model. For whoever operates the gateway, the refusal means the model deck and the integration's allow-list disagree, which is what `L-260923-2c7f6b` tracks for api-dev.

## Decisions

### D1. `model_not_allowed_error` joins the gateway's routing refusals as `MODEL_NOT_ALLOWED`

A new member, `GatewayRoutingRefusal.MODEL_NOT_ALLOWED`, is mapped from the code `"model_not_allowed_error"` in `_GATEWAY_ROUTING_REFUSAL_BY_CODE`. It classifies as `CONFIGURATION` / `CHANGE_MODEL`, is never retried, and leaves `is_model_not_found` unset.

- **Why this family.** The gateway raises it before any provider sees the request, and it concerns which model may be used. That is the family's definition: the refusal is not an inference failure and not the prompt's fault, and a retry earns the same answer. The family exists to keep such refusals away from the status-ladder arm.
- **Why the flag stays unset.** The model exists and an integration serves it; this caller may not use it there. Saying "not found" would be false, the same reasoning `WRONG_PROTOCOL` and `UNSERVED_CAPABILITY` follow. The error stays the family's failure class and carries the distinction in its advice.
- **Why match on the code alone.** Every other routing code is in the `pig-` namespace, which no vendor emits into. This one is Portkey's code, and no model vendor uses it. Portkey's cloud emits it for the integrations Pipelex configures and for a user's own workspace behind the `portkey` backend alike, and the manifold's vendored middleware emits it too. The first draft said only gateways Pipelex configures emit it, which review round 1 refuted; the conclusion stands, because the refusal means the same thing and calls for the same move from any of them, and only the advice has to hold for both (D2). The enum docstring and the map comment are rewritten to say that this member is keyed on the gateway substrate's code rather than on a `pig-NN`, and that it arrives on 412 rather than 400. Also checking the status would add nothing: both raise sites answer 412, and the remedy would be the same under any status.
- **Every Extract hop already reads the code.** The code sits in `type`, with `code: null`. The OpenAI hop reads `exc.type`, the Anthropic hop reads the body's `error.type`, and the two Pipelex-service hops read `code` and then fall back to `type`. This was probed at `85729dfd3` with the campaign's 412 body, each exception built the way production builds it: Portkey's and OpenAI's `_make_status_error_from_response` (through the test module's `_as_the_portkey_sdk_raises_it` and `_as_the_openai_sdk_raises_it`), an `httpx.HTTPStatusError` for the manifold's native routes, and `AsyncAnthropic._make_status_error_from_response`, which returns a plain `APIStatusError` for a 412. All four returned `provider_error_code = "model_not_allowed_error"`, so the change touches no Extract hop. The tests pin every hop anyway, as `TestTheCodeSurvivesEveryExtractHop` does for the other members.

### D2. The advice names the model handle

The family's advice deliberately names no model, because the gateway's own message states every specific. That reasoning fails here. The gateway's message names only the backend's wire id (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`), which the method's author never wrote. `render_inference_error` already receives `model_handle`, so it threads the handle through `_render_detail` into `_render_gateway_routing_refusal_detail`, and only this member uses it. The handle is the one the model deck resolved the pipe's model to, so a pipe that named a preset or an alias reads the handle behind it. The advice reads:

> The inference gateway does not allow the model 'claude-4.5-sonnet' for this account — pick another model for the pipe; if the pipe named this one, leaving its model unset uses the default instead. If your model deck lists it as available, the deck and the gateway's allow-list disagree: on the Pipelex gateway, contact support; on a Portkey workspace of your own, allow the model in the integration that serves it.

Both hints are conditional, which review round 1 asked for, because the Render step cannot tell the cases apart. The handle may be one the pipe named or the deck's default, and when it is the default, telling the caller to leave the model unset would tell them to do what they already did. And a deck disagreement is Pipelex's to settle on the Pipelex gateway and the user's own on their Portkey workspace, which nothing on the wire distinguishes.

The report's `model` field already carries the handle, through `fill_model_and_provider` in `LLMWorkerAbstract`. So the change is to the advice, not to attribution.

### D3. The HTTP answer does not move

At `85729dfd3` the refusal already answers 500 (`CONFIGURATION` implies `ErrorDomain.CONFIG`), and it still does after this change. Only `user_action` changes. The changelog says so, because a classification change usually moves the status.

### D4. One test pins the hand-built wrapper to what instructor really raises

pipelex#1289 rewrote `wrap_in_instructor_retry` to build the new shape by hand. `test_instructor_retry.py` pins the retry predicate against instructor's `_RETRYABLE_PARSE_ERRORS`, but nothing pins the wrapper's shape against the real loop. A hand-built exception is how cause 1 stayed green on the old lock, so the helper would drift silently at the next instructor release that changes the shape.

One test module fixes that by driving `from_openai` and `from_anthropic` over `httpx.MockTransport` with `make_instructor_schema_retrying`, in three shapes: an API error first, an invalid output followed by an API error, and a spent budget. For each shape it asserts that `extract_underlying_sdk_exception` returns the exception that ended the loop, and that the exception instructor raised matches the shape the helper builds: the SDK exception as `__cause__`, and only parse failures in `failed_attempts`. The same module drives the campaign's scenario end to end for D1.

### D5. Two statements #1289 left inaccurate are corrected

- The "`instructor` Unwrap" section of `docs/under-the-hood/error-model.md` still says that a `pydantic.ValidationError` from a schema mismatch "lands in `UNKNOWN`". It does not. `_STATUSLESS_BY_TYPE_NAME` maps it to `CONTENT` / `CHANGE_INPUT`, and the spent-budget row above shows it answering 422.
- The Unreleased changelog entry "A transport error inside a structured-output call is classified again" dates the wrapping to "`instructor` 1.16 and later". The bisection shows it started in 1.15.3. The correct range tells a reader on an older pipelex whether they were affected, since pipelex before this release accepted `instructor>=1.13`.

## What does not change

`located_failure.py` stays as it is. Its floor and fallback are right for a failure nothing classified, which a gateway refusal no longer is. Refusing, at validation time, a model the account cannot use is `L-260927-2a587b` (`pipelex-server`), and resolving every model reference to a served handle at validation is `L-260925-cfb6f3`. Both would prevent the run; this item classifies the failure when it happens anyway.

`pipelex-server`'s fixture `_MODEL_REFUSED_REPORT` (`platform/tests/unit/platform/routers/v1/test_runs.py`) records the `change_input` shape. It tests the platform's route rather than the runner's classification, so it stays green, but it will read as out of date once the server moves its `pipelex` pin.
