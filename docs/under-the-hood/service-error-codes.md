---
title: "Service Error Codes"
description: "How a plugin contributes the error codes its gateway or hosted service emits, so the runtime classifies and explains those refusals ahead of the HTTP status ladder."
---

# Service Error Codes

Not every failure on an inference call comes from a provider. A gateway, or a hosted inference service that routes to providers on the caller's behalf, may refuse a request itself, before any model sees it, under error codes of its own: a request over its size limit, a file reference it cannot resolve, a model it does not route. Those refusals arrive on statuses the [status ladder](error-model.md#worker-classification) reads as a provider rejecting the prompt, so without their codes a caller who has a reference to fix, or a deployment problem to report, is told to revise their inputs.

The plugin that speaks to such a service knows its codes, so the plugin contributes them. This page describes that seam.

## Contributing the codes

A plugin declares each code its service emits as a `ServiceErrorCode` (`pipelex.cogt.inference.service_error_vocabulary`) and hands them to the registrar in its `register`:

```python
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar

ACME_ERROR_CODES = (
    ServiceErrorCode(
        code="acme_body_too_large",
        category=InferenceErrorCategory.CONTENT,
        error_code=CoreCode.INPUT_TOO_LARGE,
        user_action_kind=UserActionKind.CHANGE_INPUT,
        detail="The request was too large for the Acme gateway — send less in one call, or use smaller inputs.",
    ),
    ServiceErrorCode(
        code="acme_unknown_model",
        category=InferenceErrorCategory.CONFIGURATION,
        error_code=CoreCode.MODEL_UNAVAILABLE,
        user_action_kind=UserActionKind.CHANGE_MODEL,
        detail="The Acme gateway does not serve that model — pick a model this deployment serves.",
        is_model_not_found=True,
    ),
)


class AcmePlugin:
    name = "acme"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_service_error_codes(codes=ACME_ERROR_CODES)
        # ...and the plugin's inference backends
```

Each entry says, about one code:

| Field | Meaning |
|-------|---------|
| `code` | the code as the service puts it on the wire, which the worker's Extract step recovers into `ProviderErrorMetadata.provider_error_code` |
| `category` | the `InferenceErrorCategory`, which decides whether the call is repeated within the run |
| `error_code` | the public registry code the rendered error carries, which decides its problem: its domain, the HTTP status it answers on a server, whether a retry can succeed, and the sentences and the step every reader of it gets. It is one of the codes every family's failure class declares (`INFERENCE_FAILURE_CODES` in `pipelex.cogt.exceptions`) |
| `user_action_kind` | the kind of the error's advice |
| `detail` | the advice itself: what the caller, or whoever operates the service, should do. The local CLIs print it as a tip beside the error; a problem never carries it, since its step is the code's. The service's message already names the specifics, so the advice need not repeat them |
| `is_model_not_found` | set for a code that means the service does not know the model at all: it selects the family's `*ModelNotFoundError` class, which the pipe layer re-raises as a model-availability error carrying the model handle, and its `error_code` is then `model.unavailable` |
| `body_params` | the parameters of `error_code` the service states in its error body, each mapped to the field holding it; empty by default. See [The facts of a refusal](#the-facts-of-a-refusal) |

## The facts of a refusal

A problem's sentences are rendered from its code's templates and its parameters, never from the service's message, which rides the operator's diagnostics alone. So a code whose sentence names facts, such as `input.too_large` ("The input '{input}' reaches {size}, past the limit of {limit}."), renders them for the caller only when the error is given them; without them the caller reads the code's title, "An input exceeds a size limit", and the problem builder logs that a required parameter is missing.

A service that knows the facts states them as fields of its error body, in its own vocabulary, and the entry maps them to the registry's names:

```python
ServiceErrorCode(
    code="acme_files_too_large",
    category=InferenceErrorCategory.CONTENT,
    error_code=CoreCode.INPUT_TOO_LARGE,
    user_action_kind=UserActionKind.CHANGE_INPUT,
    detail="The files are over the provider's limit — use smaller files.",
    body_params={"input": "reference", "size": "size_bytes", "limit": "limit_bytes"},
)
```

When a refusal matches the entry, `render_inference_error` reads each field from the body the worker's Extract step kept (`ProviderErrorMetadata.body`), in its `error` section first and then at its top level, where the OpenAI client leaves the section's fields (`error_body_sections` in `pipelex.cogt.inference.error_classification`), and gives the values it finds to the error with `with_params`. A field the body does not hold, or holds as `null`, is left out, and the problem renders the sentences its code has for the parameters it was given; a value of the wrong type is dropped and logged by the problem builder, as for any raise site. An entry naming a parameter its `error_code` does not declare is refused when it is built.

## How the runtime reads them

At boot, every plugin's contributions are frozen into one `ServiceErrorVocabulary` on the runtime hub. `classify_inference_error` consults it first, ahead of the quota rules and the status ladder, for any failure that reached an HTTP status: a code the vocabulary knows decides the category, the registry code, the action and the model-not-found flag, and `render_inference_error` constructs the family's error with that registry code and renders the entry's advice. A code nobody contributed, and every failure in a process that registered none, classifies on the status ladder as before.

**Codes are matched on the code alone, with no check on the provider.** A request reaches a service through whichever SDK its protocol calls for, so the provider a failure reports does not identify the service; the code does. A plugin that contributes a code vouches that no vendor emits it, which in practice means the codes live in a namespace of the service's own.

**For a code to reach the classifier, the worker's Extract step must recover it.** The vendor-facing distillers read an OpenAI-shaped error body's `type` before its `code`. A service that renders `{"error": {"type": "invalid_request_error", "code": "<specific_code>"}}` needs its distiller to read `code` first: `error_code_from_body_code_first` in `pipelex.cogt.inference.error_classification` does exactly that. For a plugin that distils a plain-HTTP failure itself, `retry_after_seconds_from_headers` beside it reads the delay from the response's headers, `retry-after-ms` first when it is above zero and then `Retry-After`, and `parse_retry_after_seconds` reads a lone `Retry-After` value.

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| an entry whose `error_code` no family's failure class declares, a model-not-found entry whose `error_code` is not `model.unavailable`, or a `TRANSIENT` entry whose `error_code` does not invite a retry | a validation error when the plugin builds the entry, at import |
| two plugins contribute the same code | `DuplicateServiceErrorCodeError`, naming both plugins |
| an entry whose `body_params` names a parameter its `error_code` does not declare | a validation error when the plugin builds the entry, at import |
| a plugin contributes a code the runtime classifies itself (`model_not_allowed_error`, see the [Error Model](error-model.md#a-model-the-integration-does-not-allow)) | `ReservedServiceErrorCodeError` |

The vocabulary is a kernel-layer contribution: a plugin published under `pipelex.plugins.kernel` may contribute it, since inference errors are classified in a kernel-only boot too.

## Related

- [Error Model](error-model.md) — the Extract / Classify / Render pipeline the vocabulary plugs into
- [Inference Backend Plugins](inference-backend-plugins.md) — the plugin contract and the Inference SPI
