"""The one place this backend's transport behaviour is decided.

The SDK ships a `RetryPolicy` of its own and would apply it silently. Retrying is a Pipelex
decision, so the policy is built here from the runtime's own `transport_max_retries` and handed to
the client explicitly.

**There are three timeouts in this SDK and they are not the same one.** The client carries a
timeout, the retry policy carries its own beside it, and `system_one` takes a per-call override.
Both of the first two are set here, deliberately and to the same value, so that a retried request
cannot outlive the budget the caller was promised. The per-call override is deliberately never
passed: it exists to depart from the client's settings, and this backend has no call that should.
"""

from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.config import get_config
from pipelex.providers.typesafe.typesafe_exceptions import TypesafeError

# How long one judgment may take, retries included. A single request answers in about a quarter of
# a second and fifty questions in one request answer in the same quarter, so this is a wide margin
# rather than a working budget — it is here to bound a hung connection, not to bound the model.
TYPESAFE_REQUEST_TIMEOUT_SECONDS = 60.0


def make_typesafe_client(*, backend: InferenceBackend) -> AsyncTypeSafeClient:
    """Build the shared async client for a TypeSafe backend.

    One client serves every concurrent judgment — the spike ran forty at once through a single one
    with no interference — which is why the plugin caches it in the ``SdkClientRegistry`` rather
    than building one per worker.
    """
    if backend.api_key is None:
        msg = f"Inference backend '{backend.name}' has no API key configured, so TypeSafe judgments cannot be requested"
        raise TypesafeError(msg)
    return AsyncTypeSafeClient(
        api_key=backend.api_key,
        base_url=backend.endpoint,
        retry=make_typesafe_retry_policy(),
        timeout=TYPESAFE_REQUEST_TIMEOUT_SECONDS,
    )


def make_typesafe_retry_policy() -> RetryPolicy:
    """The retry budget this backend runs under, taken from the runtime's own transport setting."""
    return RetryPolicy(
        max_retries=get_config().inference.transport_max_retries,
        timeout=TYPESAFE_REQUEST_TIMEOUT_SECONDS,
    )
