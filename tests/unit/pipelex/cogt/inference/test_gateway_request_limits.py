"""The gateway's request-shape refusals, from the wire code to the rendered advice.

The Pipelex inference gateway bounds what a request may weigh and how deeply it may
nest, and refuses anything over those bounds with codes of its own: ``pig-07`` (the
body is over its byte cap, at 413), ``pig-08`` (the body's size cannot be read — a
chunked body, or an unreadable ``Content-Length`` — at 411), ``pig-10`` (a
``pipelex-storage://`` object over its cap, at 413) and ``pig-11`` (the body nests
deeper than the gateway's depth limit, at 400).

Without a class for them the Classify step falls through to the generic status
ladder, and a caller who sent something too large reads "the provider rejected the
request" rather than "the request was too large". These tests pin the whole chain:
the code is recognized, it survives every Extract hop that can carry it, it
classifies as a caller/limit error that is never retried, and the Render step says
which limit was hit.

**The code is the discriminator, not the provider.** A request reaches the gateway
through several SDKs — the Portkey substrate, plain ``httpx`` on the native routes,
and the shared Anthropic driver that Claude travels on — so the refusal arrives
under three different ``ProviderName`` values. ``pig-`` is the gateway's own code
namespace, which is why recognition keys on it alone.
"""

from __future__ import annotations

from typing import Any

import anthropic
import httpx
import pytest
from portkey_ai.api_resources import exceptions as portkey_exc

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import (
    GatewayRequestLimit,
    ProviderErrorMetadata,
    UserActionKind,
    extract_anthropic_metadata,
    extract_gateway_metadata,
    extract_manifold_metadata,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName

_ORIGIN = "https://manifold.example.com"


def _refusal_body(message: str, code: str) -> dict[str, Any]:
    """The body the gateway's ``generateApiErrorResponse`` renders, verbatim in shape.

    ``{status, message, error: {message, code}}`` — the code lives only under
    ``error.code``, and there is no ``error.type`` beside it.
    """
    beautified = f"Portkey Error: {message}. Error Code: {code}"
    return {"status": "failure", "message": beautified, "error": {"message": beautified, "code": code}}


_BODY_TOO_LARGE_BODY = _refusal_body(
    "This request's body is 17825792 bytes, over this gateway's limit of 16777216 bytes for a body of media type application/json",
    "pig-07",
)
_LENGTH_REQUIRED_BODY = _refusal_body(
    "This gateway requires a declared Content-Length on a POST carrying a body; it does not accept a chunked body",
    "pig-08",
)
_OBJECT_TOO_LARGE_BODY = _refusal_body("The storage object is over this gateway's per-object limit", "pig-10")
_BODY_TOO_DEEP_BODY = _refusal_body("The request body nests deeper than this gateway's limit of 128 levels", "pig-11")


def _envelope(code: str | None, *, status_code: int, provider: ProviderName = ProviderName.GATEWAY) -> ProviderErrorMetadata:
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type="BadRequestError",
        message="Portkey Error: refused",
        status_code=status_code,
        provider_error_code=code,
    )


class TestTheCodeIsRecognized:
    """``gateway_request_limit`` reads the gateway's own code namespace off the envelope."""

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("pig-07", GatewayRequestLimit.BODY_TOO_LARGE),
            ("pig-08", GatewayRequestLimit.BODY_LENGTH_REQUIRED),
            ("pig-10", GatewayRequestLimit.OBJECT_TOO_LARGE),
            ("pig-11", GatewayRequestLimit.BODY_TOO_DEEP),
        ],
    )
    def test_each_limit_code_maps_to_its_kind(self, code: str, expected: GatewayRequestLimit) -> None:
        assert _envelope(code, status_code=413).gateway_request_limit == expected

    @pytest.mark.parametrize("code", [None, "pig-01", "pig-09", "invalid_request_error", "PIG-07", ""])
    def test_any_other_code_is_not_a_request_limit(self, code: str | None) -> None:
        """The gateway's routing and storage-resolution refusals are a different family, and so is a vendor's code."""
        assert _envelope(code, status_code=400).gateway_request_limit is None

    @pytest.mark.parametrize("provider", list(ProviderName))
    def test_the_code_is_read_whichever_provider_reported_it(self, provider: ProviderName) -> None:
        """Claude reaches the gateway on the Anthropic driver, so the refusal is not always reported as GATEWAY."""
        assert _envelope("pig-07", status_code=413, provider=provider).gateway_request_limit == GatewayRequestLimit.BODY_TOO_LARGE


class TestTheCodeSurvivesEveryExtractHop:
    """The refusal body the gateway actually emits, through each SDK that can carry it."""

    def test_through_the_portkey_substrate(self) -> None:
        request = httpx.Request("POST", f"{_ORIGIN}/v1/chat/completions")
        response = httpx.Response(status_code=413, request=request)
        exc = portkey_exc.BadRequestError(message="error", request=request, response=response, body=_BODY_TOO_LARGE_BODY)

        metadata = extract_gateway_metadata(exc)

        assert metadata.provider_error_code == "pig-07"
        assert metadata.gateway_request_limit == GatewayRequestLimit.BODY_TOO_LARGE

    def test_through_plain_httpx_on_the_native_routes(self) -> None:
        request = httpx.Request("POST", f"{_ORIGIN}/v1/pipelex/extract")
        response = httpx.Response(status_code=400, request=request, json=_BODY_TOO_DEEP_BODY)
        exc = httpx.HTTPStatusError("Client error '400 Bad Request'", request=request, response=response)

        metadata = extract_manifold_metadata(exc)

        assert metadata.provider_error_code == "pig-11"
        assert metadata.gateway_request_limit == GatewayRequestLimit.BODY_TOO_DEEP

    def test_through_the_shared_anthropic_driver(self) -> None:
        request = httpx.Request("POST", f"{_ORIGIN}/v1/messages")
        response = httpx.Response(status_code=413, request=request)
        exc = anthropic.BadRequestError(message="error", response=response, body=_OBJECT_TOO_LARGE_BODY)

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider_error_code == "pig-10"
        assert metadata.gateway_request_limit == GatewayRequestLimit.OBJECT_TOO_LARGE


class TestClassification:
    """A limit refusal is a caller error the runtime must not retry."""

    @pytest.mark.parametrize(
        ("code", "status_code", "expected_limit", "expected_category", "expected_action"),
        [
            ("pig-07", 413, GatewayRequestLimit.BODY_TOO_LARGE, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            (
                "pig-08",
                411,
                GatewayRequestLimit.BODY_LENGTH_REQUIRED,
                InferenceErrorCategory.CONFIGURATION,
                UserActionKind.CONTACT_SUPPORT,
            ),
            ("pig-10", 413, GatewayRequestLimit.OBJECT_TOO_LARGE, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
            ("pig-11", 400, GatewayRequestLimit.BODY_TOO_DEEP, InferenceErrorCategory.CONTENT, UserActionKind.CHANGE_INPUT),
        ],
    )
    def test_each_limit_classifies_as_a_caller_error(
        self,
        code: str,
        status_code: int,
        expected_limit: GatewayRequestLimit,
        expected_category: InferenceErrorCategory,
        expected_action: UserActionKind,
    ) -> None:
        result = classify_inference_error(_envelope(code, status_code=status_code))

        assert result.gateway_request_limit == expected_limit
        assert result.category == expected_category
        assert result.user_action_kind == expected_action
        assert result.category.is_retryable is False
        assert result.is_model_not_found is False

    def test_a_413_without_the_code_is_left_to_the_status_ladder(self) -> None:
        """Only the gateway's own code names a limit; a bare 413 from a vendor is not one."""
        result = classify_inference_error(_envelope(None, status_code=413))

        assert result.gateway_request_limit is None
        assert result.category == InferenceErrorCategory.CONFIGURATION

    def test_the_411_would_otherwise_read_as_a_configuration_error_with_input_advice(self) -> None:
        """What the fall-through gave before: the generic 4xx bucket, telling the caller to revise the prompt."""
        fell_through = classify_inference_error(_envelope("something-else", status_code=411))

        assert fell_through.user_action_kind == UserActionKind.CHANGE_INPUT


class TestRenderedAdvice:
    """Each limit gets advice naming what to do about it, not the generic rejection line."""

    @pytest.mark.parametrize(
        ("code", "status_code", "expected_phrase"),
        [
            ("pig-07", 413, "too large"),
            ("pig-08", 411, "Content-Length"),
            ("pig-10", 413, "per-file size limit"),
            ("pig-11", 400, "deeply"),
        ],
    )
    def test_the_detail_names_the_limit(self, code: str, status_code: int, expected_phrase: str) -> None:
        metadata = _envelope(code, status_code=status_code)
        classification = classify_inference_error(metadata)

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="claude-fake",
            model_handle="fake-handle",
        )

        assert rendered.user_action is not None
        assert expected_phrase in rendered.user_action.detail
        assert "review the prompt, parameters, and inputs" not in rendered.user_action.detail

    def test_the_two_size_limits_are_told_apart(self) -> None:
        """A body over its cap and one file over its cap need different remedies."""
        details: list[str] = []
        for code, status_code in (("pig-07", 413), ("pig-10", 413)):
            metadata = _envelope(code, status_code=status_code)
            rendered = render_inference_error(
                metadata=metadata,
                classification=classify_inference_error(metadata),
                family=InferenceErrorFamily.LLM,
                model_desc="claude-fake",
                model_handle="fake-handle",
            )
            assert rendered.user_action is not None
            details.append(rendered.user_action.detail)

        assert details[0] != details[1]
