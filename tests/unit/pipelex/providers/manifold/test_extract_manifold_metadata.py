"""Which header `extract_manifold_metadata` takes the request id from, and in what order.

The manifold gateway stamps its trace id on every answer a provider gave, and since the header
spellings were given a pipelex vocabulary it emits that id twice: under `x-pipelex-trace-id`, the
spelling the dialect owns, and under `x-portkey-trace-id`, the inherited one it still carries for
the vendor SDK on the image path. The two always hold the same value, so the precedence below is
not about picking the better id — it is about the moment the gateway stops emitting the vendor
spelling, after which a runtime that only knew that one would report no request id at all.

`x-request-id` stays ahead of both: it is the *provider's* own id when the provider sent one, which
is what a support conversation with that provider needs, and the gateway's trace id is the fallback
for every answer that carried none.
"""

from __future__ import annotations

import httpx

from pipelex.cogt.inference.error_classification import extract_manifold_metadata

_ORIGIN = "https://manifold.example.com"


def _refusal_with_headers(headers: dict[str, str]) -> httpx.HTTPStatusError:
    """A native-route failure as the manifold client raises it: plain httpx, no vendor SDK."""
    request = httpx.Request("POST", f"{_ORIGIN}/v1/pipelex/extract")
    response = httpx.Response(status_code=502, request=request, headers=headers)
    return httpx.HTTPStatusError("Server error '502 Bad Gateway'", request=request, response=response)


class TestTheRequestIdTheManifoldPathReports:
    def test_reads_the_pipelex_spelled_trace_id(self) -> None:
        """The spelling the dialect owns, alone on the response — where the gateway is heading."""
        metadata = extract_manifold_metadata(_refusal_with_headers({"x-pipelex-trace-id": "trace-pipelex"}))

        assert metadata.request_id == "trace-pipelex"

    def test_prefers_the_pipelex_spelling_over_the_vendor_one(self) -> None:
        """Both spellings on the wire is what the gateway emits today, with one value under each."""
        headers = {"x-portkey-trace-id": "trace-vendor", "x-pipelex-trace-id": "trace-pipelex"}

        metadata = extract_manifold_metadata(_refusal_with_headers(headers))

        assert metadata.request_id == "trace-pipelex"

    def test_still_reads_the_vendor_spelling_while_the_gateway_emits_it(self) -> None:
        """The fallback is harmless until the gateway drops the inherited spelling, and useful until then."""
        metadata = extract_manifold_metadata(_refusal_with_headers({"x-portkey-trace-id": "trace-vendor"}))

        assert metadata.request_id == "trace-vendor"

    def test_prefers_the_providers_own_request_id_over_any_trace_id(self) -> None:
        """A provider answered and named its call; that id, not the gateway's, is the one to quote."""
        headers = {"x-request-id": "provider-1", "x-pipelex-trace-id": "trace-pipelex", "x-portkey-trace-id": "trace-vendor"}

        metadata = extract_manifold_metadata(_refusal_with_headers(headers))

        assert metadata.request_id == "provider-1"

    def test_reports_no_request_id_when_no_provider_was_reached(self) -> None:
        """A refusal the gateway raised before trying a provider carries neither trace spelling."""
        metadata = extract_manifold_metadata(_refusal_with_headers({}))

        assert metadata.request_id is None
