"""How a failure on the Pipelex Manifold service's native routes is distilled into error metadata.

The native routes (``/v1/pipelex/extract``, ``/v1/pipelex/search``) are not OpenAI-shaped, so they
are called with plain ``httpx`` rather than through a vendor SDK, and their failures are distilled
here, beside the client that raises them.
"""

from __future__ import annotations

import json
from typing import Any

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, error_code_from_body_code_first, parse_retry_after_seconds
from pipelex.cogt.inference.provider_name import ProviderName

# The headers the service stamps its trace id on, in the order the distiller below reads them.
#
# Every answer a provider gave carries that id twice, with the same value under each spelling: the
# pipelex one the dialect owns, and the inherited vendor one the gateway still emits because
# `portkey_ai` reads it on the image path — a refusal the gateway raised before trying a provider
# carries neither. Reading the pipelex spelling first is what makes the gateway's eventual dropping
# of the vendor one a no-op for the native routes, at which point the second name and its lookup go
# away. It is not a no-op for the image path: `extract_gateway_metadata` carries the vendor spelling
# as a literal of its own, and the image worker distils its failures through it, so it can only move
# once the image path is off `portkey_ai`.
MANIFOLD_TRACE_ID_HEADER = "x-pipelex-trace-id"
MANIFOLD_VENDOR_TRACE_ID_HEADER = "x-portkey-trace-id"


def extract_manifold_metadata(exc: BaseException) -> ProviderErrorMetadata:
    """Distill a raw-httpx failure against the Pipelex Manifold service into metadata.

    Two exception shapes reach here:

    - ``httpx.HTTPStatusError``, which carries the whole ``response`` — status, headers, and a body
      this reads as JSON on a best-effort basis;
    - ``httpx.RequestError`` (connect, timeout, read), which carries only a request; every
      status-related field comes back as ``None``, and the class name is what the classify step
      matches on to call it a network failure.

    **The error code is read ``code`` first**, via ``error_code_from_body_code_first``, and the
    ordinary vendor-facing precedence would lose it here. A refusal these routes raise themselves is
    rendered as ``{"error": {"message": …, "type": "invalid_request_error", "code":
    "pipelex_document_too_large"}}`` — the generic bucket in ``type``, the frozen contract code the
    classifier actually needs in ``code`` — so reading ``type`` first replaces every ``pipelex_*``
    code with ``invalid_request_error``. The gateway's fail-closed ``pig-0N`` shape carries no
    ``type`` at all, so it reads the same either way.

    **The request id is read in the manifold dialect's own spelling.** The provider's ``x-request-id``
    comes first when a provider named its call, and the gateway's trace id is the fallback for the
    answers that carried none — under ``MANIFOLD_TRACE_ID_HEADER`` before the inherited vendor
    spelling, which holds the same value and is only still read because the gateway still emits it.

    **It reports ``ProviderName.GATEWAY``**, and that is a decision rather than an oversight: the
    service is a gateway, it phrases quota exhaustion and rate limiting the way the gateway
    substrate does, and every ``match`` on ``ProviderName`` would need a second arm with the same
    body to say otherwise. Which service answered is already carried by the error's model handle
    and backend name.
    """
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        status_code = None
    headers = getattr(response, "headers", None)
    request_id: str | None = None
    retry_after_seconds: float | None = None
    if headers is not None:
        request_id_value = headers.get("x-request-id") or headers.get(MANIFOLD_TRACE_ID_HEADER) or headers.get(MANIFOLD_VENDOR_TRACE_ID_HEADER)
        if isinstance(request_id_value, str):
            request_id = request_id_value
        retry_after_seconds = parse_retry_after_seconds(headers.get("retry-after"))
    body: Any | None = None
    if response is not None:
        try:
            body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            # A refusal the service did not render as JSON is still a refusal; the status code and
            # the message carry it, and insisting on a body here would trade a classified error for
            # a decode error raised while classifying one.
            body = None
    provider_error_code = error_code_from_body_code_first(body)
    return ProviderErrorMetadata(
        provider=ProviderName.GATEWAY,
        sdk_exception_type=type(exc).__name__,
        message=str(exc),
        status_code=status_code,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        provider_error_code=provider_error_code,
        body=body,
    )
