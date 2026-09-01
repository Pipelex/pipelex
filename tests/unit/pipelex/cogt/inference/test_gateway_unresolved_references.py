"""The gateway's unresolvable-reference refusals, from the wire code to the rendered advice.

A request may name a file rather than carry it — a ``pipelex-storage://`` key the
Pipelex inference gateway resolves for the caller, or a document URL it fetches on
their behalf. When it cannot turn that reference into bytes it refuses the request
itself, with codes of its own: ``pig-09`` on the LLM routes, where its ``pig-0N``
family has one fail-closed slot for "cannot resolve" and the message carries the
difference, and a named ``pipelex_*`` contract code on the native
``/v1/pipelex/*`` routes for each distinct cause.

Without a class for them the Classify step falls through to the generic status
ladder — every one of these arrives on 400 — so a caller who mistyped a storage
key, pointed at an object this deployment cannot read, or aimed a URL at a host the
SSRF guard refuses reads "the provider rejected the request — review the prompt,
parameters, and inputs". These tests pin the whole chain: the code is recognized,
it survives every Extract hop that can carry it, it classifies as a caller error
that is never retried, and the Render step says which reference failed and what to
do about it.

**Grouped by remedy, not by wire code.** Two codes share a ``GatewayUnresolvedReference``
member only when the caller's next move is the same — which is why the three
document-URL refusals are one member and ``pipelex_document_host_refused`` is its
own: the caller can act on all four, but only the host refusal has to be stated as
the deliberate security policy it is, rather than as a fault to work around.

**And one member is not the caller's at all.** ``pipelex_storage_uri_unsupported``
means no bucket is configured, so this deployment does not serve the scheme —
nothing about the inputs causes it and no input avoids it. It is the family's one
``CONTACT_SUPPORT`` arm, the same call ``BODY_LENGTH_REQUIRED`` gets among the
request limits.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx
import pytest
from openai import OpenAI
from portkey_ai import Portkey

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import (
    GatewayRequestLimit,
    GatewayUnresolvedReference,
    ProviderErrorMetadata,
    UserActionKind,
    extract_anthropic_metadata,
    extract_gateway_metadata,
    extract_manifold_metadata,
    extract_openai_metadata,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName

_ORIGIN = "https://manifold.example.com"

# Every code in the family, paired with the member it must reach. Reused by the
# recognition, classification and rendering cases so a code added to the map
# without an arm — or an arm added without a code — cannot pass unnoticed.
_EVERY_CODE_AND_MEMBER: list[tuple[str, GatewayUnresolvedReference]] = [
    ("pig-09", GatewayUnresolvedReference.REFERENCE_UNRESOLVED),
    ("pipelex_storage_uri_invalid", GatewayUnresolvedReference.STORAGE_REFERENCE_INVALID),
    ("pipelex_storage_unreadable", GatewayUnresolvedReference.STORAGE_OBJECT_UNREADABLE),
    ("pipelex_storage_uri_unsupported", GatewayUnresolvedReference.STORAGE_NOT_SERVED),
    ("pipelex_document_scheme_refused", GatewayUnresolvedReference.DOCUMENT_URL_REFUSED),
    ("pipelex_document_address_refused", GatewayUnresolvedReference.DOCUMENT_URL_REFUSED),
    ("pipelex_document_redirect_refused", GatewayUnresolvedReference.DOCUMENT_URL_REFUSED),
    ("pipelex_document_host_refused", GatewayUnresolvedReference.DOCUMENT_HOST_REFUSED),
    ("pipelex_document_unreachable", GatewayUnresolvedReference.DOCUMENT_UNREACHABLE),
    ("pipelex_document_empty", GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE),
    ("pipelex_document_unsupported_type", GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE),
    ("pipelex_document_bad_data_url", GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE),
]

# The same codes as a flat list, for the cases that only need the wire code.
_EVERY_CODE: list[str] = [pair[0] for pair in _EVERY_CODE_AND_MEMBER]

# Every code whose remedy is the caller's own, i.e. all of them but the one that
# says this deployment serves no storage at all.
_CALLER_FIXABLE_CODES: list[str] = [code for code, member in _EVERY_CODE_AND_MEMBER if member is not GatewayUnresolvedReference.STORAGE_NOT_SERVED]

_GENERIC_ADVICE = "The provider rejected the request — review the prompt, parameters, and inputs."


def _fail_closed_refusal_body(message: str, code: str) -> dict[str, Any]:
    """The body the gateway's ``generateApiErrorResponse`` renders, verbatim in shape.

    ``{status, message, error: {message, code}}`` — the code lives only under
    ``error.code``, and there is no ``error.type`` beside it. This is how the LLM
    routes speak, so it is the envelope ``pig-09`` arrives in.
    """
    beautified = f"Portkey Error: {message}. Error Code: {code}"
    return {"status": "failure", "message": beautified, "error": {"message": beautified, "code": code}}


def _native_route_refusal_body(message: str, code: str) -> dict[str, Any]:
    """The body pig's native ``/v1/pipelex/*`` routes render, verbatim in shape.

    ``providerErrorResponse`` puts a generic ``invalid_request_error`` in
    ``error.type`` and the frozen contract code in ``error.code``, which is why the
    two Pipelex-service Extract hops read ``code`` before ``type``. Every
    ``pipelex_*`` code in this family arrives in this envelope.
    """
    return {
        "error": {"message": message, "type": "invalid_request_error", "param": None, "code": code},
        "provider": "linkup",
    }


_UNRESOLVED_BODY = _fail_closed_refusal_body(
    "The request refers to 'pipelex-storage://nope/missing.pdf', which this gateway cannot resolve",
    "pig-09",
)


def _as_the_portkey_sdk_raises_it(*, status_code: int, body: dict[str, Any]) -> BaseException:
    """Build the exception through Portkey's own factory rather than by hand.

    The constructor accepts any ``body`` you give it; the SDK's factory does not —
    it sets ``body`` to ``json.loads(text)["error"]["message"]``, a string. Only the
    factory reproduces what the Extract step actually receives in production.
    """
    request = httpx.Request("POST", f"{_ORIGIN}/v1/chat/completions")
    response = httpx.Response(
        status_code=status_code,
        request=request,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    client = Portkey(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1")
    return client._make_status_error_from_response(request=request, response=response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _as_the_openai_sdk_raises_it(*, status_code: int, body: dict[str, Any]) -> BaseException:
    """Build the exception through the OpenAI SDK's own factory, for the same reason as above.

    This is the hop a gateway or manifold *chat* call actually takes: both plugins
    build an ``OpenAICompletionsLLMWorker`` / ``OpenAIResponsesLLMWorker`` over a
    client pointed at the service, so an LLM-route refusal is distilled by
    ``extract_openai_metadata`` and never by ``extract_gateway_metadata``.
    """
    request = httpx.Request("POST", f"{_ORIGIN}/v1/chat/completions")
    response = httpx.Response(
        status_code=status_code,
        request=request,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    client = OpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1")
    return client._make_status_error_from_response(response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _envelope(code: str | None, *, status_code: int = 400, provider: ProviderName = ProviderName.GATEWAY) -> ProviderErrorMetadata:
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type="BadRequestError",
        message="Portkey Error: refused",
        status_code=status_code,
        provider_error_code=code,
    )


def _rendered_detail(metadata: ProviderErrorMetadata, *, family: InferenceErrorFamily = InferenceErrorFamily.LLM) -> str:
    rendered = render_inference_error(
        metadata=metadata,
        classification=classify_inference_error(metadata),
        family=family,
        model_desc="claude-fake",
        model_handle="fake-handle",
    )
    assert rendered.user_action is not None
    return rendered.user_action.detail


class TestTheCodeIsRecognized:
    """``gateway_unresolved_reference`` reads the gateway's own code namespace off the envelope."""

    @pytest.mark.parametrize(("code", "expected"), _EVERY_CODE_AND_MEMBER)
    def test_each_code_maps_to_its_member(self, code: str, expected: GatewayUnresolvedReference) -> None:
        assert _envelope(code).gateway_unresolved_reference == expected

    @pytest.mark.parametrize("member", list(GatewayUnresolvedReference))
    def test_every_member_is_reachable_from_a_wire_code(self, member: GatewayUnresolvedReference) -> None:
        """A member no code reaches is dead advice — it would never render for anyone."""
        assert member in {expected for _, expected in _EVERY_CODE_AND_MEMBER}

    @pytest.mark.parametrize(
        "code",
        [None, "pig-01", "pig-07", "pig-10", "invalid_request_error", "PIG-09", "pipelex_storage_object_too_large", ""],
    )
    def test_any_other_code_is_not_an_unresolved_reference(self, code: str | None) -> None:
        """The routing codes, the request-shape limits, and a vendor's own code are all other families."""
        assert _envelope(code).gateway_unresolved_reference is None

    @pytest.mark.parametrize("provider", list(ProviderName))
    def test_the_code_is_read_whichever_provider_reported_it(self, provider: ProviderName) -> None:
        """Claude reaches the gateway on the Anthropic driver, so the refusal is not always reported as GATEWAY."""
        metadata = _envelope("pipelex_document_host_refused", provider=provider)

        assert metadata.gateway_unresolved_reference == GatewayUnresolvedReference.DOCUMENT_HOST_REFUSED


class TestTheCodeSurvivesEveryExtractHop:
    """The refusal body the gateway actually emits, through each SDK that can carry it."""

    def test_through_the_portkey_substrate(self) -> None:
        exc = _as_the_portkey_sdk_raises_it(status_code=400, body=_UNRESOLVED_BODY)

        metadata = extract_gateway_metadata(exc)

        assert metadata.provider_error_code == "pig-09"
        assert metadata.gateway_unresolved_reference == GatewayUnresolvedReference.REFERENCE_UNRESOLVED

    def test_the_portkey_substrate_discards_the_payload_and_the_code_survives_anyway(self) -> None:
        """The reason the hop above is built through the SDK rather than by hand.

        Portkey's ``_make_status_error_from_response`` puts the *message string* on
        ``exc.body``, never the document — so a test that hands the constructor a
        nested dict passes on a shape production never produces, while the real path
        recovers no code at all.
        """
        exc = _as_the_portkey_sdk_raises_it(status_code=400, body=_UNRESOLVED_BODY)

        assert isinstance(getattr(exc, "body", None), str)
        assert extract_gateway_metadata(exc).gateway_unresolved_reference == GatewayUnresolvedReference.REFERENCE_UNRESOLVED

    def test_the_native_envelope_survives_the_portkey_substrate_too(self) -> None:
        """A gateway extract reaches Azure Document Intelligence in the chat costume.

        The refusal is rendered by ``providerErrorResponse`` — the ``type``-bearing
        native envelope — and then raised by Portkey's factory, which replaces the
        payload with the message string. Recovering the code needs the response
        fallback *and* the ``code``-first precedence.
        """
        body = _native_route_refusal_body("that host is refused", "pipelex_document_host_refused")
        exc = _as_the_portkey_sdk_raises_it(status_code=400, body=body)

        metadata = extract_gateway_metadata(exc)

        assert metadata.provider_error_code == "pipelex_document_host_refused"
        assert metadata.gateway_unresolved_reference == GatewayUnresolvedReference.DOCUMENT_HOST_REFUSED

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("pipelex_storage_uri_invalid", GatewayUnresolvedReference.STORAGE_REFERENCE_INVALID),
            ("pipelex_storage_unreadable", GatewayUnresolvedReference.STORAGE_OBJECT_UNREADABLE),
            ("pipelex_document_unsupported_type", GatewayUnresolvedReference.DOCUMENT_CONTENT_UNUSABLE),
        ],
    )
    def test_through_plain_httpx_on_the_native_routes(self, code: str, expected: GatewayUnresolvedReference) -> None:
        """Where the ``pipelex_*`` codes are actually raised: ``/v1/pipelex/extract`` and its siblings."""
        request = httpx.Request("POST", f"{_ORIGIN}/v1/pipelex/extract")
        response = httpx.Response(status_code=400, request=request, json=_native_route_refusal_body("refused", code))
        exc = httpx.HTTPStatusError("Client error '400 Bad Request'", request=request, response=response)

        metadata = extract_manifold_metadata(exc)

        assert metadata.provider_error_code == code
        assert metadata.gateway_unresolved_reference == expected

    def test_through_the_shared_anthropic_driver(self) -> None:
        """Claude travels on the vendor's own SDK, which recovers the code from the body it kept."""
        request = httpx.Request("POST", f"{_ORIGIN}/v1/messages")
        response = httpx.Response(status_code=400, request=request)
        exc = anthropic.BadRequestError(message="error", response=response, body=_UNRESOLVED_BODY)

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider_error_code == "pig-09"
        assert metadata.gateway_unresolved_reference == GatewayUnresolvedReference.REFERENCE_UNRESOLVED

    def test_through_the_openai_substrate_that_carries_every_chat_call(self) -> None:
        """The hop a gateway or manifold LLM call actually takes.

        That hop reads ``type`` before ``code``, which is right for the vendor it
        also serves — it recovers ``pig-09`` because the fail-closed envelope
        carries no ``type`` at all. That is a property of the gateway's envelope, so
        it is checked here rather than assumed.
        """
        exc = _as_the_openai_sdk_raises_it(status_code=400, body=_UNRESOLVED_BODY)

        metadata = extract_openai_metadata(exc)

        assert metadata.gateway_unresolved_reference == GatewayUnresolvedReference.REFERENCE_UNRESOLVED


class TestClassification:
    """An unresolvable reference is a caller error the runtime must not retry."""

    @pytest.mark.parametrize(("code", "expected"), _EVERY_CODE_AND_MEMBER)
    def test_each_code_classifies_as_its_member_and_is_never_retried(self, code: str, expected: GatewayUnresolvedReference) -> None:
        result = classify_inference_error(_envelope(code))

        assert result.gateway_unresolved_reference == expected
        assert result.category.is_retryable is False
        assert result.is_model_not_found is False
        assert result.gateway_request_limit is None

    @pytest.mark.parametrize("code", _CALLER_FIXABLE_CODES)
    def test_a_reference_the_caller_can_repair_asks_them_to_change_the_input(self, code: str) -> None:
        result = classify_inference_error(_envelope(code))

        assert result.category == InferenceErrorCategory.CONTENT
        assert result.user_action_kind == UserActionKind.CHANGE_INPUT

    def test_a_deployment_that_serves_no_storage_is_an_operators_problem(self) -> None:
        """No bucket configured is not something any input can avoid, so the caller is not asked to try."""
        result = classify_inference_error(_envelope("pipelex_storage_uri_unsupported"))

        assert result.gateway_unresolved_reference == GatewayUnresolvedReference.STORAGE_NOT_SERVED
        assert result.category == InferenceErrorCategory.CONFIGURATION
        assert result.user_action_kind == UserActionKind.CONTACT_SUPPORT
        assert result.category.is_retryable is False

    def test_a_plain_400_without_a_recognized_code_still_takes_the_status_ladder(self) -> None:
        """Only the gateway's own codes name a reference; a bare 400 from a vendor does not."""
        result = classify_inference_error(_envelope("something-else"))

        assert result.gateway_unresolved_reference is None
        assert result.category == InferenceErrorCategory.CONTENT
        assert result.user_action_kind == UserActionKind.CHANGE_INPUT


class TestRenderedAdvice:
    """Each member gets advice naming what to do about the reference, not the generic rejection line."""

    @pytest.mark.parametrize("code", _EVERY_CODE)
    def test_no_member_renders_the_generic_rejection_line(self, code: str) -> None:
        """The whole point: every one of these used to read as a prompt to revise."""
        assert _rendered_detail(_envelope(code)) != _GENERIC_ADVICE

    @pytest.mark.parametrize(
        ("code", "expected_phrase"),
        [
            ("pig-09", "could not be resolved"),
            ("pipelex_storage_uri_invalid", "malformed"),
            ("pipelex_storage_unreadable", "does not exist or cannot be read"),
            ("pipelex_storage_uri_unsupported", "contact support"),
            ("pipelex_document_scheme_refused", "http(s) URL"),
            ("pipelex_document_host_refused", "security policy"),
            ("pipelex_document_unreachable", "publicly reachable"),
            ("pipelex_document_empty", "fetched but cannot be used"),
        ],
    )
    def test_the_detail_names_the_remedy(self, code: str, expected_phrase: str) -> None:
        assert expected_phrase in _rendered_detail(_envelope(code))

    def test_the_host_refusal_is_stated_as_a_security_policy(self) -> None:
        """The distinction the whole ``DOCUMENT_HOST_REFUSED`` member exists to keep.

        The SSRF guard refused deliberately. Advice that reads as a fault to work
        around — revise the prompt, use a smaller file — sends the caller looking
        for a problem in a document that is perfectly fine.
        """
        detail = _rendered_detail(_envelope("pipelex_document_host_refused"))

        assert "security policy" in detail
        assert "prompt" not in detail
        assert "smaller" not in detail

    def test_the_unserved_scheme_does_not_ask_the_caller_to_fix_their_input(self) -> None:
        detail = _rendered_detail(_envelope("pipelex_storage_uri_unsupported"))

        assert "contact support" in detail
        assert "prompt" not in detail

    def test_the_two_storage_reference_failures_are_told_apart(self) -> None:
        """A key that is malformed and an object that is not there need different checks."""
        malformed = _rendered_detail(_envelope("pipelex_storage_uri_invalid"))
        unreadable = _rendered_detail(_envelope("pipelex_storage_unreadable"))

        assert malformed != unreadable

    def test_the_three_document_url_refusals_share_one_remedy(self) -> None:
        """They are one member precisely because the caller's next move is the same."""
        details = {
            _rendered_detail(_envelope(code))
            for code in ("pipelex_document_scheme_refused", "pipelex_document_address_refused", "pipelex_document_redirect_refused")
        }

        assert len(details) == 1

    def test_a_host_refusal_reaching_an_extract_reads_the_same(self) -> None:
        """The document-fetch codes arrive on extract calls, so the advice must not assume an LLM family."""
        metadata = _envelope("pipelex_document_host_refused")

        assert _rendered_detail(metadata, family=InferenceErrorFamily.EXTRACT) == _rendered_detail(metadata)


class TestTheTwoGatewayFamiliesDoNotShadowEachOther:
    """One bounds the request's shape, the other says a reference could not be resolved.

    The same middleware raises ``pig-09`` and ``pig-10``, and the native routes'
    storage codes sit in one frozen contract — so the two maps are neighbours in the
    same namespace and a code landing in both would silently give one family's
    advice to the other's refusal.
    """

    @pytest.mark.parametrize("code", _EVERY_CODE)
    def test_no_unresolved_reference_code_is_also_a_request_limit(self, code: str) -> None:
        assert _envelope(code).gateway_request_limit is None

    @pytest.mark.parametrize("code", ["pig-07", "pig-08", "pig-10", "pig-11", "pipelex_storage_object_too_large", "pipelex_document_too_large"])
    def test_no_request_limit_code_is_also_an_unresolved_reference(self, code: str) -> None:
        assert _envelope(code, status_code=413).gateway_unresolved_reference is None

    def test_the_storage_codes_are_split_between_the_two_families_on_the_same_route(self) -> None:
        """Both arrive from ``/v1/pipelex/extract``, and each must reach its own family."""
        too_large = _envelope("pipelex_storage_object_too_large", status_code=413)
        unreadable = _envelope("pipelex_storage_unreadable")

        assert classify_inference_error(too_large).gateway_request_limit == GatewayRequestLimit.OBJECT_TOO_LARGE
        assert classify_inference_error(too_large).gateway_unresolved_reference is None
        assert classify_inference_error(unreadable).gateway_unresolved_reference == GatewayUnresolvedReference.STORAGE_OBJECT_UNREADABLE
        assert classify_inference_error(unreadable).gateway_request_limit is None
