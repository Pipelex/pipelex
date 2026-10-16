# Service Error Codes

Not every failure on an inference call comes from a provider. A gateway, or a hosted inference service that routes to providers on the caller's behalf, may refuse a request itself, before any model sees it, under error codes of its own: a request over its size limit, a file reference it cannot resolve, a model it does not route. Those refusals arrive on statuses the [status ladder](error-model.md#worker-classification) reads as a provider rejecting the prompt, so without their codes a caller who has a reference to fix, or a deployment problem to report, is told to revise their inputs.

The plugin that speaks to such a service knows its codes, so the plugin contributes them. This page describes that seam.

## Contributing the codes

A plugin declares each code its service emits as a `ServiceErrorCode` (`pipelex.cogt.inference.service_error_vocabulary`) and hands them to the registrar in its `register`:

```python
from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.cogt.inference.service_error_vocabulary import ServiceErrorCode
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import PluginRegistrar

ACME_ERROR_CODES = (
    ServiceErrorCode(
        code="acme_body_too_large",
        category=InferenceErrorCategory.CONTENT,
        user_action_kind=UserActionKind.CHANGE_INPUT,
        detail="The request was too large for the Acme gateway — send less in one call, or use smaller inputs.",
    ),
    ServiceErrorCode(
        code="acme_unknown_model",
        category=InferenceErrorCategory.CONFIGURATION,
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

Each entry says four things about one code:

| Field | Meaning |
|-------|---------|
| `code` | the code as the service puts it on the wire, which the worker's Extract step recovers into `ProviderErrorMetadata.provider_error_code` |
| `category` | the `InferenceErrorCategory`, which decides whether the error is retried and the HTTP status it answers on a server |
| `user_action_kind` | the kind of advice the caller gets |
| `detail` | the advice itself, rendered beside the service's own message: what the caller, or whoever operates the service, should do. The service's message already names the specifics, so the advice need not repeat them |
| `is_model_not_found` | set for a code that means the service does not know the model at all: it selects the family's `*ModelNotFoundError` class, which the pipe layer re-raises as a model-availability error carrying the model handle |

## How the runtime reads them

At boot, every plugin's contributions are frozen into one `ServiceErrorVocabulary` on the runtime hub. `classify_inference_error` consults it first, ahead of the quota rules and the status ladder, for any failure that reached an HTTP status: a code the vocabulary knows decides the category, the action and the model-not-found flag, and `render_inference_error` renders the entry's advice. A code nobody contributed, and every failure in a process that registered none, classifies on the status ladder as before.

**Codes are matched on the code alone, with no check on the provider.** A request reaches a service through whichever SDK its protocol calls for, so the provider a failure reports does not identify the service; the code does. A plugin that contributes a code vouches that no vendor emits it, which in practice means the codes live in a namespace of the service's own.

**For a code to reach the classifier, the worker's Extract step must recover it.** The vendor-facing distillers read an OpenAI-shaped error body's `type` before its `code`. A service that renders `{"error": {"type": "invalid_request_error", "code": "<specific_code>"}}` needs its distiller to read `code` first: `error_code_from_body_code_first` in `pipelex.cogt.inference.error_classification` does exactly that, and `parse_retry_after_seconds` beside it reads a `Retry-After` header, for a plugin that distils a plain-HTTP failure itself.

## Fail-loud guarantees

| Condition | Error |
|-----------|-------|
| two plugins contribute the same code | `DuplicateServiceErrorCodeError`, naming both plugins |
| a plugin contributes a code the runtime classifies itself (`model_not_allowed_error`, see the [Error Model](error-model.md#a-model-the-integration-does-not-allow)) | `ReservedServiceErrorCodeError` |

The vocabulary is a kernel-layer contribution: a plugin published under `pipelex.plugins.kernel` may contribute it, since inference errors are classified in a kernel-only boot too.

## Related

- [Error Model](error-model.md) — the Extract / Classify / Render pipeline the vocabulary plugs into
- [Inference Backend Plugins](inference-backend-plugins.md) — the plugin contract and the Inference SPI
