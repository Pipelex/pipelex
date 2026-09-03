"""The endpoint rule, and the fallback that must not exist.

The backend declares the Pipelex Manifold service's **origin** — scheme, host and port, with no
version segment — and each client appends what its own SDK expects beneath it. The rule is normative
rather than advisory because getting it wrong is not loud: a `/v1`-suffixed endpoint under the
Anthropic SDK produces `POST /v1/v1/messages`, which a gateway forwards and a provider answers with
a 200-shaped failure.

**The absent-endpoint case is the one worth a test of its own.** The Portkey-path sibling reads
`backend.endpoint or PORTKEY_GATEWAY_URL`, which is correct there — an unset endpoint means "use the
vendor's cloud". The same line on this path would mean that an empty-resolving
`PIPELEX_MANIFOLD_ENDPOINT` silently builds a client aimed at `api.portkey.ai` carrying the
*manifold* service token: a live billable request to the wrong vendor, with nothing anywhere
reporting it. There is no symptom to notice, which is why the refusal is pinned here.
"""

from __future__ import annotations

import pytest

from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.providers.manifold.manifold_exceptions import ManifoldCredentialsError, ManifoldEndpointError
from pipelex.providers.manifold.manifold_factory import ManifoldFactory

_ORIGIN = "https://manifold.example.com"
_TOKEN = "manifold-service-token"


def _backend(*, endpoint: str | None = _ORIGIN, api_key: str | None = _TOKEN) -> InferenceBackend:
    return InferenceBackend(name="pipelex_manifold", endpoint=endpoint, api_key=api_key)


class TestManifoldEndpointRule:
    def test_origin_is_returned_as_declared(self) -> None:
        assert ManifoldFactory.get_origin(_backend()) == _ORIGIN

    @pytest.mark.parametrize("declared", [f"{_ORIGIN}/", f"{_ORIGIN}///", f"  {_ORIGIN}  "])
    def test_a_trailing_slash_or_surrounding_space_is_forgiven(self, declared: str) -> None:
        """The one shape of a correct answer a human types by accident, normalized rather than refused."""
        assert ManifoldFactory.get_origin(_backend(endpoint=declared)) == _ORIGIN

    def test_the_version_segment_is_appended_by_the_factory_not_the_operator(self) -> None:
        assert ManifoldFactory.get_base_url(_backend()) == f"{_ORIGIN}/v1"

    @pytest.mark.parametrize("declared", [None, "", "   ", "/"], ids=["unset", "empty", "blank", "slash-only"])
    def test_an_absent_endpoint_is_refused_and_never_defaulted(self, declared: str | None) -> None:
        with pytest.raises(ManifoldEndpointError) as exc_info:
            ManifoldFactory.get_origin(_backend(endpoint=declared))

        # The vendor's cloud must appear nowhere in the outcome — neither as a value nor as a hint.
        assert "portkey" not in exc_info.value.message.lower()
        assert "PIPELEX_MANIFOLD_ENDPOINT" in exc_info.value.message

    def test_an_absent_api_key_is_refused_by_name(self) -> None:
        with pytest.raises(ManifoldCredentialsError, match="PIPELEX_MANIFOLD_API_KEY"):
            ManifoldFactory.get_api_key(_backend(api_key=None))

    def test_the_only_header_about_us_is_the_service_token(self) -> None:
        """One header, no routing.

        The manifold dialect says nothing on the wire about which provider should serve a model —
        the service decides that from the model id in the body and refuses a client that tries to
        say otherwise. Asserting the whole dict rather than one key is what makes a header added
        later a red test rather than a silent widening.
        """
        assert ManifoldFactory.make_auth_headers(_backend()) == {"x-pipelex-api-key": _TOKEN}
