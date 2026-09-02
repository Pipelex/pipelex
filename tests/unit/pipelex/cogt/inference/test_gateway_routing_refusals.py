"""The gateway's routing refusals, from the wire code to the rendered advice.

Before a request can reach a provider the Pipelex inference gateway has to decide
*which* provider: it reads the model out of the request, looks it up in its own
routing table, and hands the call to the integration that serves it. When that
resolution fails it refuses the request itself, with codes of its own — ``pig-01``
when it serves no such model, ``pig-02`` when the model's integration is switched
off for want of a credential, ``pig-05`` when a native-protocol path names a model
another provider serves, and ``pig-06`` when a model reaches a route its provider
does not serve.

Every one of them answers HTTP 400, so without a class for them the Classify step
falls through to the status ladder's 400 arm and a caller who named a model the
deployment does not serve is told *"The provider rejected the request — review the
prompt, parameters, and inputs."* — and receives an ``LLMCompletionError`` rather
than the ``LLMModelNotFoundError`` that case has always produced when the model
deck itself cannot find a model. These tests pin the whole chain: the code is
recognized, it survives every Extract hop that can carry it, it classifies as a
configuration problem that is never retried, the Render step says which routing
decision failed and who has to change what, and both consequences of the category
that outlive this module are pinned too — the HTTP status the family now answers,
and the advice surviving the pipe layer's re-raise.

**Every member is its own wire code here**, unlike the two families beside it.
That is not an accident of the code space: grouping is by remedy in all three
families, and each of these four names a different thing that has to change.

**Only ``pig-01`` sets ``is_model_not_found``.** The flag is not a category — it
selects the family's ``*ModelNotFoundError`` class, which ``pipe_operator.py``
re-raises as a ``PipeOperatorModelAvailabilityError`` carrying the model handle.
``pig-01`` is literally "this deployment does not know that model", seen from the
gateway. For ``pig-05`` and ``pig-06`` the model exists and *is* served — it just
cannot do what was asked, or was asked over the wrong protocol — so claiming it
was not found would be false.

**``pig-02`` is the family's ``CONTACT_SUPPORT`` arm.** A switched-off integration
is the gateway operator's fact: nothing about the request causes it, none of the
caller's own credentials are at fault, and sending them shopping for another model
would hide an unset variable. The same call ``STORAGE_NOT_SERVED`` and
``BODY_LENGTH_REQUIRED`` get in the two families beside this one.

**``pig-03`` and ``pig-04`` are deliberately outside the family**, and that scope
decision is pinned below rather than left to a comment. Neither is produced today
by a client talking to a Pipelex-operated gateway: ``pig-03`` refuses client-side
routing forms that
``tests/unit/pipelex/providers/manifold/test_manifold_clients.py`` pins the
manifold clients against by name, and ``pig-04`` refuses a path the gateway does
not mount at all. Two limits on the first half, recorded beside the map rather
than implied here: that test names four headers while the gateway refuses on an
allow-list, and the gateway img-gen worker does send ``x-portkey-config``, which
Portkey's cloud reads and one of our gateways would refuse.

**``pig-05`` is mapped but unreachable from today's runtime**, which is why no
Extract hop is pinned for it. It is raised only on a native Google protocol path
(``/v1/<v1|v1alpha|v1beta>/models/<model>:generateContent`` or its
``streamGenerateContent`` twin), and no worker speaks that protocol to
the gateway: both the gateway and manifold plugins build their LLM workers on the
OpenAI substrate, and ``ManifoldNativeClient`` serves only the ``/v1/pipelex/*``
extract and search routes. The map entry costs nothing and is right the day a
native Google path is wired — but the Google Extract hop would not carry the code
even then, which the last case in ``TestTheCodeSurvivesEveryExtractHop`` pins as
the trap it is.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx
import pytest
from openai import OpenAI
from portkey_ai import Portkey

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    _GATEWAY_ROUTING_REFUSAL_BY_CODE,  # pyright: ignore[reportPrivateUsage]
    GatewayRoutingRefusal,
    ProviderErrorMetadata,
    UserActionKind,
    extract_anthropic_metadata,
    extract_gateway_metadata,
    extract_google_metadata,
    extract_manifold_metadata,
    extract_openai_metadata,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.system.pipe_run_mode import PipeRunMode

_ORIGIN = "https://manifold.example.com"

# Every code in the family, paired with the member it must reach. Reused by the
# recognition, classification and rendering cases so a code added to the map
# without an arm — or an arm added without a code — cannot pass unnoticed.
_EVERY_CODE_AND_MEMBER: list[tuple[str, GatewayRoutingRefusal]] = [
    ("pig-01", GatewayRoutingRefusal.UNKNOWN_MODEL),
    ("pig-02", GatewayRoutingRefusal.DISABLED_INTEGRATION),
    ("pig-05", GatewayRoutingRefusal.WRONG_PROTOCOL),
    ("pig-06", GatewayRoutingRefusal.UNSERVED_CAPABILITY),
]

# The same codes as a flat list, for the cases that only need the wire code.
_EVERY_CODE: list[str] = [pair[0] for pair in _EVERY_CODE_AND_MEMBER]

# Every member whose remedy is picking a different model, i.e. all of them but the
# one that means an operator never enabled the integration.
_CHANGE_MODEL_CODES: list[str] = [code for code, member in _EVERY_CODE_AND_MEMBER if member is not GatewayRoutingRefusal.DISABLED_INTEGRATION]

# The gateway's request-shape limits and its unresolvable-reference codes, for the
# three-way disjointness cases.
_REQUEST_LIMIT_CODES: list[str] = ["pig-07", "pig-08", "pig-10", "pig-11", "pipelex_storage_object_too_large", "pipelex_document_too_large"]
_UNRESOLVED_REFERENCE_CODES: list[str] = ["pig-09", "pipelex_storage_uri_invalid", "pipelex_storage_unreadable", "pipelex_document_host_refused"]

_GENERIC_ADVICE = "The provider rejected the request — review the prompt, parameters, and inputs."
_GENERIC_NOT_FOUND_ADVICE = "The requested model was not found — pick an available model."


def _fail_closed_refusal_body(message: str, code: str) -> dict[str, Any]:
    """The body the gateway's ``generateApiErrorResponse`` renders, verbatim in shape.

    ``{status, message, error: {message, code}}`` — the code lives only under
    ``error.code``, and there is no ``error.type`` beside it. Every routing refusal
    is rendered by that one helper, on the LLM routes and the native ones alike, so
    this is the only envelope the family arrives in.
    """
    beautified = f"Portkey Error: {message}. Error Code: {code}"
    return {"status": "failure", "message": beautified, "error": {"message": beautified, "code": code}}


_UNKNOWN_MODEL_BODY = _fail_closed_refusal_body("No model found for the request", "pig-01")


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


def _rendered_error(metadata: ProviderErrorMetadata, *, family: InferenceErrorFamily = InferenceErrorFamily.LLM) -> CogtError:
    return render_inference_error(
        metadata=metadata,
        classification=classify_inference_error(metadata),
        family=family,
        model_desc="claude-fake",
        model_handle="fake-handle",
    )


def _rendered_detail(metadata: ProviderErrorMetadata, *, family: InferenceErrorFamily = InferenceErrorFamily.LLM) -> str:
    rendered = _rendered_error(metadata, family=family)
    assert rendered.user_action is not None
    return rendered.user_action.detail


class TestTheCodeIsRecognized:
    """``gateway_routing_refusal`` reads the gateway's own code namespace off the envelope."""

    @pytest.mark.parametrize(("code", "expected"), _EVERY_CODE_AND_MEMBER)
    def test_each_code_maps_to_its_member(self, code: str, expected: GatewayRoutingRefusal) -> None:
        assert _envelope(code).gateway_routing_refusal == expected

    @pytest.mark.parametrize("member", list(GatewayRoutingRefusal))
    def test_every_member_is_reachable_from_a_wire_code(self, member: GatewayRoutingRefusal) -> None:
        """A member no code reaches is dead advice — it would never render for anyone."""
        assert member in {expected for _, expected in _EVERY_CODE_AND_MEMBER}

    def test_the_table_covers_the_whole_production_map(self) -> None:
        """The other direction, which the per-code cases cannot see.

        Every case in this module walks the table above into the map. Without this
        one, a code added to the map and forgotten here would be classified and
        rendered in production and exercised by nothing.
        """
        assert set(_EVERY_CODE) == set(_GATEWAY_ROUTING_REFUSAL_BY_CODE)

    @pytest.mark.parametrize(
        "code",
        [None, "pig-07", "pig-09", "pig-11", "invalid_request_error", "PIG-01", "pipelex_storage_unreadable", "model_not_found", ""],
    )
    def test_any_other_code_is_not_a_routing_refusal(self, code: str | None) -> None:
        """The request-shape limits, the unresolvable references, and a vendor's own code are all other families."""
        assert _envelope(code).gateway_routing_refusal is None

    @pytest.mark.parametrize("provider", list(ProviderName))
    def test_the_code_is_read_whichever_provider_reported_it(self, provider: ProviderName) -> None:
        """Claude reaches the gateway on the Anthropic driver, so the refusal is not always reported as GATEWAY."""
        metadata = _envelope("pig-01", provider=provider)

        assert metadata.gateway_routing_refusal == GatewayRoutingRefusal.UNKNOWN_MODEL


class TestTheCodeSurvivesEveryExtractHop:
    """The refusal body the gateway actually emits, through each SDK that can carry it."""

    def test_through_the_portkey_substrate(self) -> None:
        exc = _as_the_portkey_sdk_raises_it(status_code=400, body=_UNKNOWN_MODEL_BODY)

        metadata = extract_gateway_metadata(exc)

        assert metadata.provider_error_code == "pig-01"
        assert metadata.gateway_routing_refusal == GatewayRoutingRefusal.UNKNOWN_MODEL

    def test_the_portkey_substrate_discards_the_payload_and_the_code_survives_anyway(self) -> None:
        """The reason the hop above is built through the SDK rather than by hand.

        Portkey's ``_make_status_error_from_response`` puts the *message string* on
        ``exc.body``, never the document — so a test that hands the constructor a
        nested dict passes on a shape production never produces, while the real path
        recovers no code at all.
        """
        exc = _as_the_portkey_sdk_raises_it(status_code=400, body=_UNKNOWN_MODEL_BODY)

        assert isinstance(getattr(exc, "body", None), str)
        assert extract_gateway_metadata(exc).gateway_routing_refusal == GatewayRoutingRefusal.UNKNOWN_MODEL

    @pytest.mark.parametrize(("code", "expected"), _EVERY_CODE_AND_MEMBER)
    def test_through_the_openai_substrate_that_carries_every_chat_call(self, code: str, expected: GatewayRoutingRefusal) -> None:
        """The hop a gateway or manifold LLM call actually takes.

        That hop reads ``type`` before ``code``, which is right for the vendor it
        also serves — it recovers these because the fail-closed envelope carries no
        ``type`` at all. That is a property of the gateway's envelope rather than of
        the hop, so it is checked here rather than assumed.
        """
        exc = _as_the_openai_sdk_raises_it(status_code=400, body=_fail_closed_refusal_body("refused", code))

        assert extract_openai_metadata(exc).gateway_routing_refusal == expected

    def test_through_plain_httpx_on_the_native_routes(self) -> None:
        """Where ``pig-06`` is actually raised: ``/v1/pipelex/extract`` and its siblings.

        The route's model-versus-capability refusal is rendered by the same
        fail-closed helper as the LLM routes' — it is a ``pig-0N`` code, not one of
        the native routes' own ``pipelex_*`` contract codes.
        """
        request = httpx.Request("POST", f"{_ORIGIN}/v1/pipelex/extract")
        response = httpx.Response(status_code=400, request=request, json=_fail_closed_refusal_body("provider does not serve extract", "pig-06"))
        exc = httpx.HTTPStatusError("Client error '400 Bad Request'", request=request, response=response)

        metadata = extract_manifold_metadata(exc)

        assert metadata.provider_error_code == "pig-06"
        assert metadata.gateway_routing_refusal == GatewayRoutingRefusal.UNSERVED_CAPABILITY

    def test_through_the_shared_anthropic_driver(self) -> None:
        """Claude travels on the vendor's own SDK, which recovers the code from the body it kept."""
        request = httpx.Request("POST", f"{_ORIGIN}/v1/messages")
        response = httpx.Response(status_code=400, request=request)
        exc = anthropic.BadRequestError(message="error", response=response, body=_UNKNOWN_MODEL_BODY)

        metadata = extract_anthropic_metadata(exc)

        assert metadata.provider_error_code == "pig-01"
        assert metadata.gateway_routing_refusal == GatewayRoutingRefusal.UNKNOWN_MODEL

    def test_the_google_hop_would_not_carry_a_gateway_code_and_nothing_reaches_it_today(self) -> None:
        """``pig-05``'s hop, pinned as the trap it is rather than as a passing path.

        ``pig-05`` is raised only on the native Google protocol path, and no worker
        speaks that protocol to the gateway today — both service plugins build their
        LLM workers on the OpenAI substrate, and ``ManifoldNativeClient`` serves only
        the ``/v1/pipelex/*`` routes. So the map entry is correct and unreachable.

        Were that path wired, the code would still not arrive: Google's Extract hop
        reads the symbolic ``status`` a Google error carries (``RESOURCE_EXHAUSTED``
        and friends), and the gateway's envelope has no ``error.status`` — only a
        top-level ``status: "failure"``, which the hop dutifully returns as though it
        were a provider code. This asserts that, so whoever wires a native Google
        path finds the requirement stated rather than a silent misclassification.
        """

        class _GoogleApiError(Exception):
            """The shape ``extract_google_metadata`` reads: ``code`` is the HTTP status, ``details`` the raw body."""

            def __init__(self, *, details: dict[str, Any]) -> None:
                super().__init__("Portkey Error: refused. Error Code: pig-05")
                self.code = 400
                self.details = details
                self.response = None

        metadata = extract_google_metadata(_GoogleApiError(details=_fail_closed_refusal_body("wrong protocol", "pig-05")))

        assert metadata.provider_error_code == "failure"
        assert metadata.gateway_routing_refusal is None


class TestClassification:
    """A routing refusal is a configuration problem the runtime must not retry."""

    @pytest.mark.parametrize(("code", "expected"), _EVERY_CODE_AND_MEMBER)
    def test_each_code_classifies_as_its_member_and_is_never_retried(self, code: str, expected: GatewayRoutingRefusal) -> None:
        result = classify_inference_error(_envelope(code))

        assert result.gateway_routing_refusal == expected
        assert result.category == InferenceErrorCategory.CONFIGURATION
        assert result.category.is_retryable is False
        assert result.gateway_request_limit is None
        assert result.gateway_unresolved_reference is None

    @pytest.mark.parametrize("code", _CHANGE_MODEL_CODES)
    def test_a_refusal_the_caller_can_route_around_asks_them_to_change_the_model(self, code: str) -> None:
        result = classify_inference_error(_envelope(code))

        assert result.user_action_kind == UserActionKind.CHANGE_MODEL

    def test_a_disabled_integration_is_an_operators_problem(self) -> None:
        """The credential is the gateway operator's and unset; the caller's own key is fine."""
        result = classify_inference_error(_envelope("pig-02"))

        assert result.gateway_routing_refusal == GatewayRoutingRefusal.DISABLED_INTEGRATION
        assert result.user_action_kind == UserActionKind.CONTACT_SUPPORT
        assert result.is_model_not_found is False

    @pytest.mark.parametrize("code", _EVERY_CODE)
    def test_only_the_unknown_model_is_a_missing_model(self, code: str) -> None:
        """The flag selects the ``*ModelNotFoundError`` class, so setting it wrongly makes the runtime lie.

        For ``pig-05`` and ``pig-06`` the model exists and is served — it just
        cannot do what was asked, or was asked over the wrong protocol.
        """
        result = classify_inference_error(_envelope(code))

        assert result.is_model_not_found is (code == "pig-01")

    def test_a_plain_400_without_a_recognized_code_still_takes_the_status_ladder(self) -> None:
        """Only the gateway's own codes name a routing decision; a bare 400 from a vendor does not."""
        result = classify_inference_error(_envelope("something-else"))

        assert result.gateway_routing_refusal is None
        assert result.category == InferenceErrorCategory.CONTENT
        assert result.user_action_kind == UserActionKind.CHANGE_INPUT


class TestEndToEnd:
    """The headline of the bug: what a caller actually receives, built the way production builds it."""

    def test_an_unserved_model_reaches_the_caller_as_a_model_not_found_carrying_the_handle(self) -> None:
        """Before this family it was an ``LLMCompletionError`` telling them to review their prompt.

        The handle matters as much as the class: ``pipe_operator.py`` re-raises a
        ``ModelNotFoundError`` as a ``PipeOperatorModelAvailabilityError`` carrying
        it, which is the pipe-level error a caller already gets when the deck itself
        cannot find a model.
        """
        exc = _as_the_portkey_sdk_raises_it(status_code=400, body=_UNKNOWN_MODEL_BODY)
        metadata = extract_gateway_metadata(exc)

        rendered = render_inference_error(
            metadata=metadata,
            classification=classify_inference_error(metadata),
            family=InferenceErrorFamily.LLM,
            model_desc="some-model",
            model_handle="some-handle",
        )

        assert isinstance(rendered, LLMModelNotFoundError)
        assert rendered.model_handle == "some-handle"
        assert rendered.error_category == InferenceErrorCategory.CONFIGURATION

    def test_a_wrong_protocol_refusal_does_not_claim_the_model_was_not_found(self) -> None:
        """The model exists and is served — only the protocol the runtime spoke was wrong."""
        exc = _as_the_portkey_sdk_raises_it(status_code=400, body=_fail_closed_refusal_body("served by another provider", "pig-05"))
        metadata = extract_gateway_metadata(exc)
        classification = classify_inference_error(metadata)

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.LLM,
            model_desc="some-model",
            model_handle="some-handle",
        )

        assert isinstance(rendered, LLMCompletionError)
        assert not isinstance(rendered, LLMModelNotFoundError)
        assert classification.user_action_kind == UserActionKind.CHANGE_MODEL
        assert rendered.user_action is not None
        assert "not found" not in rendered.user_action.detail


class TestRenderedAdvice:
    """Each member gets advice naming what has to change, not a generic rejection line."""

    @pytest.mark.parametrize("code", _EVERY_CODE)
    def test_no_member_renders_the_generic_rejection_line(self, code: str) -> None:
        """The whole point: every one of these used to read as a prompt to revise."""
        assert _rendered_detail(_envelope(code)) != _GENERIC_ADVICE

    @pytest.mark.parametrize("code", _EVERY_CODE)
    def test_no_member_renders_the_generic_action_kind_advice_either(self, code: str) -> None:
        """Branching ahead of the action kind is what this asserts.

        ``CHANGE_MODEL`` alone would render "the requested model was not found" for
        three members whose model exists, and ``CONTACT_SUPPORT`` alone would render
        "the error could not be classified" for a refusal that named itself exactly.
        """
        detail = _rendered_detail(_envelope(code))

        assert detail != _GENERIC_NOT_FOUND_ADVICE
        assert "could not be classified" not in detail

    @pytest.mark.parametrize(
        ("code", "expected_phrase"),
        [
            ("pig-01", "does not serve that model"),
            ("pig-02", "has not enabled"),
            ("pig-05", "not over the protocol"),
            ("pig-06", "does not serve that capability"),
        ],
    )
    def test_the_detail_names_the_remedy(self, code: str, expected_phrase: str) -> None:
        assert expected_phrase in _rendered_detail(_envelope(code))

    def test_the_unserved_model_and_the_wrong_protocol_are_told_apart(self) -> None:
        """A model the gateway does not serve and one it serves differently need different moves."""
        unknown = _rendered_detail(_envelope("pig-01"))
        wrong_protocol = _rendered_detail(_envelope("pig-05"))

        assert unknown != wrong_protocol
        assert "does not serve that model" in unknown
        assert "serves that model" in wrong_protocol

    def test_the_disabled_integration_blames_neither_the_prompt_nor_the_callers_key(self) -> None:
        """The distinction the ``CONTACT_SUPPORT`` ruling exists to keep.

        ``CHECK_CREDENTIALS`` would send a hosted caller to rotate a perfectly valid
        key, and ``CHANGE_MODEL`` would send them shopping for a model over an
        operator's unset variable.
        """
        detail = _rendered_detail(_envelope("pig-02"))

        assert "contact support" in detail.lower()
        assert "prompt" not in detail
        assert "pick a model" not in detail

    def test_the_deck_disagreement_refusals_name_the_deck(self) -> None:
        """Advice saying only "pick another model" would send an operator hunting for a model problem.

        The runtime picks the protocol and the route from its own deck, so these two
        usually mean the deck and the gateway's routing table disagree.
        """
        for code in ("pig-05", "pig-06"):
            assert "model deck" in _rendered_detail(_envelope(code))

    def test_an_unserved_capability_reaching_an_extract_reads_the_same(self) -> None:
        """``pig-06`` arrives on extract and search calls, so the advice must not assume an LLM family."""
        metadata = _envelope("pig-06")

        assert _rendered_detail(metadata, family=InferenceErrorFamily.EXTRACT) == _rendered_detail(metadata)


class TestTheScopeDecisionIsPinned:
    """``pig-03`` and ``pig-04`` are routing codes the runtime deliberately does not map.

    Neither is producible by the clients the runtime ships, so the status ladder's
    reading of each is as good as any. These assert family membership only — they
    take no position on the verdict the ladder gives them, which for ``pig-04``'s
    404 is model-not-found and wrong in kind.
    """

    @pytest.mark.parametrize(("code", "status_code"), [("pig-03", 400), ("pig-04", 404)])
    def test_the_unmapped_routing_codes_are_not_routing_refusals(self, code: str, status_code: int) -> None:
        metadata = _envelope(code, status_code=status_code)

        assert metadata.gateway_routing_refusal is None
        assert classify_inference_error(metadata).gateway_routing_refusal is None

    def test_the_unmapped_routing_codes_belong_to_no_gateway_family_at_all(self) -> None:
        """Not quietly picked up by one of the neighbouring maps either."""
        for code, status_code in (("pig-03", 400), ("pig-04", 404)):
            metadata = _envelope(code, status_code=status_code)

            assert metadata.gateway_request_limit is None
            assert metadata.gateway_unresolved_reference is None


class TestTheThreeGatewayFamiliesDoNotShadowEachOther:
    """One bounds the request's shape, one says a reference could not be resolved, one says it could not be routed.

    All three read the same ``pig-`` namespace, so a code landing in two maps would
    silently give one family's advice to another's refusal — and the branch order in
    ``classify_inference_error`` would start to matter, which it must not.
    """

    @pytest.mark.parametrize("code", _EVERY_CODE)
    def test_no_routing_code_belongs_to_another_family(self, code: str) -> None:
        metadata = _envelope(code)

        assert metadata.gateway_request_limit is None
        assert metadata.gateway_unresolved_reference is None

    @pytest.mark.parametrize("code", _REQUEST_LIMIT_CODES + _UNRESOLVED_REFERENCE_CODES)
    def test_no_other_familys_code_is_a_routing_refusal(self, code: str) -> None:
        assert _envelope(code, status_code=413).gateway_routing_refusal is None

    def test_the_three_maps_are_disjoint_as_sets(self) -> None:
        """The direction the per-code cases cannot see: a code added to two maps at once."""
        from pipelex.cogt.inference.error_classification import (  # ruff: ignore[import-outside-top-level]
            _GATEWAY_REQUEST_LIMIT_BY_CODE,  # pyright: ignore[reportPrivateUsage]
            _GATEWAY_UNRESOLVED_REFERENCE_BY_CODE,  # pyright: ignore[reportPrivateUsage]
        )

        limits = set(_GATEWAY_REQUEST_LIMIT_BY_CODE)
        references = set(_GATEWAY_UNRESOLVED_REFERENCE_BY_CODE)
        routing = set(_GATEWAY_ROUTING_REFUSAL_BY_CODE)

        assert limits & references == set()
        assert limits & routing == set()
        assert references & routing == set()


class TestWhatTheFamilyAnswersOverHTTP:
    """The category is not only advice — it decides the status an HTTP surface returns.

    ``CONFIGURATION`` implies ``ErrorDomain.CONFIG``, which
    ``error_domain_to_http_status`` renders as 500; the ``CONTENT`` these four used
    to receive implies ``INPUT`` and renders as 422. So classifying the family
    moved its HTTP answer as surely as it moved its wording, and that is the half a
    classification test cannot see. 500 is also the status outer clients retry,
    which is worth pinning precisely because "never retried" elsewhere in this
    module is a statement about ``InferenceErrorCategory.is_retryable`` inside this
    process and about nothing else.
    """

    @pytest.mark.parametrize("code", _EVERY_CODE)
    def test_every_member_answers_500_rather_than_the_422_it_used_to(self, code: str) -> None:
        report = _rendered_error(_envelope(code)).to_error_report()

        assert report.error_domain == ErrorDomain.CONFIG
        assert report.http_status == 500

    def test_an_unrecognized_400_still_answers_422(self) -> None:
        """The contrast that makes the case above a change rather than a constant."""
        report = _rendered_error(_envelope("something-else")).to_error_report()

        assert report.error_domain == ErrorDomain.INPUT
        assert report.http_status == 422


class TestTheAdviceSurvivesThePipeBoundary:
    """``pig-01`` is the one member whose error class is re-raised on the way out.

    ``pipe_operator.py`` catches ``ModelNotFoundError`` and re-raises it as a
    ``PipeOperatorModelAvailabilityError``, whose constructor takes a message, a
    handle and a stack and no user action — so the advice reaches a caller only
    because ``_enrich_error_report_from_cause`` inherits ``user_action`` and
    ``error_domain`` off the ``__cause__`` chain. That inheritance is what carries
    every word of this family's most-argued detail through the pipe layer, and
    nothing else in this module crosses that boundary to see it.
    """

    def _re_raised_as_the_pipe_operator_does(self, cause: LLMModelNotFoundError) -> PipeOperatorModelAvailabilityError:
        """Mirror ``PipeOperator``'s ``except ModelNotFoundError`` arm, ``from`` included.

        The ``from`` is the load-bearing part: without it there is no ``__cause__``
        and the enrichment this class exists to pin has nothing to read.
        """
        try:
            raise cause
        except LLMModelNotFoundError as model_not_found_error:
            try:
                raise PipeOperatorModelAvailabilityError(
                    message=model_not_found_error.message,
                    run_mode=PipeRunMode.LIVE,
                    pipe_type="PipeLLM",
                    pipe_code="some_pipe",
                    pipe_stack=[],
                    model_handle=model_not_found_error.model_handle,
                ) from model_not_found_error
            except PipeOperatorModelAvailabilityError as availability_error:
                return availability_error

    def test_the_unknown_model_advice_reaches_the_caller_through_the_pipe_error(self) -> None:
        rendered = _rendered_error(_envelope("pig-01"))
        assert isinstance(rendered, LLMModelNotFoundError)

        report = self._re_raised_as_the_pipe_operator_does(rendered).to_error_report()

        assert report.error_type == "PipeOperatorModelAvailabilityError"
        assert report.user_action_detail() == _rendered_detail(_envelope("pig-01"))
        assert report.error_domain == ErrorDomain.CONFIG
        assert report.http_status == 500
