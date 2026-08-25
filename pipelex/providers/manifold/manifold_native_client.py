"""The HTTP client for the Pipelex Manifold service's own routes.

``POST /v1/pipelex/extract`` and ``POST /v1/pipelex/search`` are not OpenAI-shaped — they serve
document extraction and web search as themselves rather than dressed as chat completions — so they
are called with plain ``httpx`` rather than through a vendor SDK wrapped around a chat body.

**Building the request by hand is what makes the wire readable.** Two properties of the manifold
dialect live in this one method and can be asserted in a test that reads the request it built: the
only header about us is the service token, and the body carries the model with nothing about
routing. A client whose constructor defaults decide the headers cannot say that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from pipelex.cogt.inference.error_classification import extract_manifold_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.inference.transport_retry import request_with_transport_retry
from pipelex.config import get_config
from pipelex.providers.manifold.manifold_exceptions import ManifoldError
from pipelex.providers.manifold.manifold_factory import ManifoldFactory

if TYPE_CHECKING:
    from pipelex.cogt.inference.error_render import InferenceErrorFamily
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec

# Generous, and deliberately so: a deep web search or a many-page extraction is a slow call, and the
# runtime's own job-level timeouts are the ones that should bound it. Matches the SDK-less image
# path's floor rather than inventing a second number.
MANIFOLD_NATIVE_TIMEOUT_SECONDS = 600.0


class ManifoldNativeClient:
    """One route call, one dict back — or a categorized inference error."""

    def __init__(self, *, backend: InferenceBackend) -> None:
        self.base_url = ManifoldFactory.get_base_url(backend=backend)
        self.auth_headers = ManifoldFactory.make_auth_headers(backend=backend)

    async def post_json(
        self,
        *,
        route: str,
        body: dict[str, Any],
        family: InferenceErrorFamily,
        inference_model: InferenceModelSpec,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{route}"

        async def _send() -> httpx.Response:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={**self.auth_headers, "Content-Type": "application/json"},
                    json=body,
                    timeout=MANIFOLD_NATIVE_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                return response

        try:
            # These are billable, non-idempotent POSTs — a search that reached the provider has been
            # paid for — so an ambiguous 5xx is not retried. The retry stays on the failures that
            # prove no work was done.
            http_response = await request_with_transport_retry(
                send_request=_send,
                max_retries=get_config().inference.transport_max_retries,
                retry_on_ambiguous_failure=False,
            )
        except httpx.HTTPError as exc:
            metadata = extract_manifold_metadata(exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=family,
                model_desc=inference_model.desc,
                model_handle=inference_model.name,
            ) from exc

        try:
            payload: Any = http_response.json()
        except ValueError as exc:
            # A 2xx whose body is not JSON — an intermediary's error page is how this happens. Left
            # raw it is neither a `PipelexError` nor annotated with the model, so it would escape
            # the Temporal error bridge and be retried against a call that was already paid for.
            msg = f"The Pipelex Manifold service returned a non-JSON body for model '{inference_model.name}'"
            raise ManifoldError(msg) from exc
        if not isinstance(payload, dict):
            msg = f"The Pipelex Manifold service returned a '{type(payload).__name__}' rather than an object for model '{inference_model.name}'"
            raise ManifoldError(msg)
        return payload  # pyright: ignore[reportUnknownVariableType]
