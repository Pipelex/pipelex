"""A model an integration serves but does not allow for this caller, from the wire code to the rendered advice.

``model_not_allowed_error`` comes from the Portkey substrate a hosted gateway is
built on, not from any one service's own code namespace: its middleware answers it,
at HTTP 412, when an integration serves the model but does not allow it for this
caller, because the model is off the integration's allow-list or archived. The same
code comes from a hosted gateway and from a user's own Portkey workspace, so the
runtime reads it in core, through ``ProviderErrorMetadata.is_model_not_allowed``,
rather than through a plugin's service error vocabulary.

The ladder's generic 4xx arm would read a 412 as a configuration problem with the
advice to review the prompt. These tests pin the whole chain: the code is
recognized, it survives every Extract hop that can carry it, it classifies as a
configuration problem that asks for another model and is never retried, the Render
step names the model handle the deck resolved to, and the consequences that outlive
this module are pinned too — the HTTP status it answers, and the advice surviving
the pipe router's location of the failure.

**Not a missing model.** The model exists and an integration serves it, only not for
this caller, so ``is_model_not_found`` stays unset and the family keeps its failure
class rather than its ``*ModelNotFoundError``.

**The one refusal whose advice names the model.** The substrate's own message names
only the backend's wire id, which the method's author never wrote, so the advice
names the model handle the deck resolved the pipe's model to.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import anthropic
import httpx
import pytest
from openai import OpenAI
from portkey_ai import Portkey

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory, LLMCompletionError, LLMModelNotFoundError
from pipelex.cogt.inference.error_classification import (
    MODEL_NOT_ALLOWED_ERROR_CODE,
    ProviderErrorMetadata,
    UserActionKind,
    extract_anthropic_metadata,
    extract_gateway_metadata,
    extract_openai_metadata,
)
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.system.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from collections.abc import Callable

_ORIGIN = "https://gateway.example.com"

_GENERIC_ADVICE = "The provider rejected the request — review the prompt, parameters, and inputs."

# The backend's id for the model, which is all the substrate's own message names, and
# the handle the deck resolved the method's model to, which is the deck's own name for it.
_MODEL_NOT_ALLOWED_WIRE_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
_MODEL_NOT_ALLOWED_HANDLE = "claude-4.5-sonnet"

# The body the Portkey middleware answers with, at HTTP 412, verbatim as a run on the
# hosted API received it. The code sits in ``type`` and ``code`` is null.
_MODEL_NOT_ALLOWED_BODY: dict[str, Any] = {
    "error": {
        "message": f"Model {_MODEL_NOT_ALLOWED_WIRE_ID} is not allowed for this integration",
        "type": "model_not_allowed_error",
        "param": None,
        "code": None,
    }
}


def _as_the_portkey_sdk_raises_it(*, status_code: int, body: dict[str, Any]) -> BaseException:
    """Build the exception through Portkey's own factory, which keeps only the message string on ``body``."""
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
    """Build the exception through the OpenAI SDK's own factory, the hop an LLM call on a gateway takes."""
    request = httpx.Request("POST", f"{_ORIGIN}/v1/chat/completions")
    response = httpx.Response(
        status_code=status_code,
        request=request,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    client = OpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1")
    return client._make_status_error_from_response(response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _as_the_anthropic_sdk_raises_it(*, status_code: int, body: dict[str, Any]) -> BaseException:
    """Build the exception through the Anthropic SDK's own factory, the hop Claude travels on.

    For a status it has no subclass for, 412 among them, the factory returns a plain
    ``APIStatusError``, which a hand-built ``BadRequestError`` would not show.
    """
    request = httpx.Request("POST", f"{_ORIGIN}/v1/messages")
    response = httpx.Response(
        status_code=status_code,
        request=request,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    client = anthropic.AsyncAnthropic(api_key="unused-in-this-test", base_url=_ORIGIN)
    return client._make_status_error_from_response(response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _envelope(code: str | None, *, status_code: int = 412, provider: ProviderName = ProviderName.GATEWAY) -> ProviderErrorMetadata:
    return ProviderErrorMetadata(
        provider=provider,
        sdk_exception_type="PreconditionFailedError",
        message="Portkey Error: refused",
        status_code=status_code,
        provider_error_code=code,
    )


def _rendered_error(
    metadata: ProviderErrorMetadata,
    *,
    family: InferenceErrorFamily = InferenceErrorFamily.LLM,
    model_handle: str = _MODEL_NOT_ALLOWED_HANDLE,
) -> CogtError:
    return render_inference_error(
        metadata=metadata,
        classification=classify_inference_error(metadata),
        family=family,
        model_desc=f"{model_handle} → Model[{_MODEL_NOT_ALLOWED_WIRE_ID}]",
        model_handle=model_handle,
    )


def _rendered_detail(metadata: ProviderErrorMetadata, *, family: InferenceErrorFamily = InferenceErrorFamily.LLM) -> str:
    rendered = _rendered_error(metadata, family=family)
    assert rendered.user_action is not None
    return rendered.user_action.detail


class TestTheCodeIsRecognized:
    """``is_model_not_allowed`` reads the substrate's code off the envelope."""

    def test_the_code_is_recognized(self) -> None:
        assert MODEL_NOT_ALLOWED_ERROR_CODE == "model_not_allowed_error"
        assert _envelope(MODEL_NOT_ALLOWED_ERROR_CODE).is_model_not_allowed is True

    @pytest.mark.parametrize(
        "code",
        [None, "rate_limit_exceeded", "invalid_request_error", "model_not_found", "model_not_allowed", "MODEL_NOT_ALLOWED_ERROR", ""],
    )
    def test_any_other_code_is_not_a_model_not_allowed_refusal(self, code: str | None) -> None:
        assert _envelope(code).is_model_not_allowed is False

    @pytest.mark.parametrize("provider", list(ProviderName))
    def test_the_code_is_read_whichever_provider_reported_it(self, provider: ProviderName) -> None:
        """Claude reaches a gateway on the Anthropic driver, so the refusal is not always reported as GATEWAY."""
        assert _envelope(MODEL_NOT_ALLOWED_ERROR_CODE, provider=provider).is_model_not_allowed is True


class TestTheCodeSurvivesEveryExtractHop:
    @pytest.mark.parametrize(
        ("raise_it", "extract"),
        [
            pytest.param(_as_the_openai_sdk_raises_it, extract_openai_metadata, id="openai-substrate"),
            pytest.param(_as_the_anthropic_sdk_raises_it, extract_anthropic_metadata, id="anthropic-driver"),
            pytest.param(_as_the_portkey_sdk_raises_it, extract_gateway_metadata, id="portkey-substrate"),
        ],
    )
    def test_the_refusal_through_every_hop(
        self,
        raise_it: Callable[..., BaseException],
        extract: Callable[[BaseException], ProviderErrorMetadata],
    ) -> None:
        """The substrate's own envelope, at 412, through each SDK's own factory.

        Its code sits in ``type`` with ``code`` null, so every hop must find it there.
        """
        exc = raise_it(status_code=412, body=_MODEL_NOT_ALLOWED_BODY)

        metadata = extract(exc)

        assert metadata.status_code == 412
        assert metadata.provider_error_code == MODEL_NOT_ALLOWED_ERROR_CODE
        assert metadata.is_model_not_allowed is True


class TestClassification:
    def test_it_asks_for_another_model_and_is_not_a_missing_model(self) -> None:
        """The model exists and an integration serves it, only not for this caller.

        So ``CHANGE_MODEL`` is what the caller can do, and the flag stays unset:
        "not found" would be false.
        """
        result = classify_inference_error(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE))

        assert result.is_model_not_allowed is True
        assert result.category == InferenceErrorCategory.CONFIGURATION
        assert result.category.is_retryable is False
        assert result.user_action_kind == UserActionKind.CHANGE_MODEL
        assert result.is_model_not_found is False
        assert result.service_error_code is None

    def test_a_412_without_the_code_still_takes_the_status_ladder(self) -> None:
        """The contrast: the ladder's generic 4xx arm, which is what the refusal would otherwise read as."""
        result = classify_inference_error(_envelope("something-else"))

        assert result.is_model_not_allowed is False
        assert result.category == InferenceErrorCategory.CONFIGURATION
        assert result.user_action_kind == UserActionKind.CHANGE_INPUT


class TestEndToEnd:
    def test_it_reaches_the_caller_as_a_change_model_naming_the_handle(self) -> None:
        """The refusal a run on the hosted API received, through the hop an LLM call on a gateway takes.

        It asks for another model, names it by its handle, and stays the family's
        failure class, since the model was found.
        """
        exc = _as_the_openai_sdk_raises_it(status_code=412, body=_MODEL_NOT_ALLOWED_BODY)
        metadata = extract_openai_metadata(exc)

        rendered = _rendered_error(metadata)

        assert isinstance(rendered, LLMCompletionError)
        assert not isinstance(rendered, LLMModelNotFoundError)
        assert rendered.error_category == InferenceErrorCategory.CONFIGURATION
        assert rendered.user_action is not None
        assert rendered.user_action.kind == UserActionKind.CHANGE_MODEL
        assert f"'{_MODEL_NOT_ALLOWED_HANDLE}'" in rendered.user_action.detail
        assert rendered.user_action.detail != _GENERIC_ADVICE


class TestRenderedAdvice:
    def test_the_detail_names_the_remedy(self) -> None:
        assert "does not allow the model" in _rendered_detail(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE))

    def test_the_advice_names_the_handle_and_not_the_wire_id(self) -> None:
        """The substrate's message names only the backend's id, which the method's author never wrote."""
        detail = _rendered_detail(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE))

        assert f"'{_MODEL_NOT_ALLOWED_HANDLE}'" in detail
        assert _MODEL_NOT_ALLOWED_WIRE_ID not in detail
        assert "pick another model" in detail
        assert "prompt" not in detail

    def test_the_advice_offers_the_default_only_when_the_pipe_named_the_model(self) -> None:
        """The Render step cannot tell a model the pipe named from the deck's default.

        When the default is the refused model, an unconditional "leave the pipe's
        model unset" would tell the caller to do what they already did.
        """
        detail = _rendered_detail(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE))

        assert "if the pipe named this one, leaving its model unset uses the default" in detail

    def test_the_advice_says_who_settles_a_deck_disagreement_on_either_kind_of_gateway(self) -> None:
        """The same code comes from a hosted gateway and from a user's own Portkey workspace.

        Nothing on the wire tells them apart, so advice that only said "contact
        support" would send the owner of a Portkey workspace to support for a setting
        in their own dashboard.
        """
        detail = _rendered_detail(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE))

        assert "model deck" in detail
        assert "on a hosted gateway, contact support" in detail
        assert "on a Portkey workspace of your own, allow the model in the integration that serves it" in detail

    def test_the_advice_reads_the_same_on_an_extract(self) -> None:
        metadata = _envelope(MODEL_NOT_ALLOWED_ERROR_CODE)

        assert _rendered_detail(metadata, family=InferenceErrorFamily.EXTRACT) == _rendered_detail(metadata)


class TestWhatItAnswersOverHTTP:
    def test_it_answers_500_as_an_unrecognized_412_does(self) -> None:
        """At its real status the refusal's answer does not move: only its advice does.

        The ladder's generic 4xx arm already reads a 412 as ``CONFIGURATION``, so
        recognizing the code changes this refusal's ``user_action`` and nothing about
        its status.
        """
        report = _rendered_error(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE)).to_error_report()
        unrecognized_report = _rendered_error(_envelope("something-else")).to_error_report()

        assert report.error_domain == ErrorDomain.CONFIG
        assert report.http_status == 500
        assert unrecognized_report.error_domain == ErrorDomain.CONFIG
        assert unrecognized_report.http_status == 500


class TestTheAdviceSurvivesThePipeBoundary:
    def test_the_advice_reaches_the_caller_through_the_located_failure(self) -> None:
        """The failure class is not re-raised by the pipe operator, so the router's location is the boundary.

        ``PipeRouterError`` reports the root fault located at the failing pipe, with
        the classification its cause chain carries. When nothing on the chain carried
        a user action, that report would fall back to "the message gives the cause".
        """
        rendered = _rendered_error(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE))
        located = PipeRouterError.make_located(
            failure=rendered,
            run_mode=PipeRunMode.LIVE,
            pipe_code="score_lead",
            output_name=None,
            pipe_stack=["score_lead"],
        )
        located.__cause__ = rendered

        report = located.to_error_report()

        assert report.error_type == "LLMCompletionError"
        assert report.error_domain == ErrorDomain.CONFIG
        assert report.error_category == InferenceErrorCategory.CONFIGURATION
        assert report.retryable is False
        assert report.user_action is not None
        assert report.user_action.kind == UserActionKind.CHANGE_MODEL
        assert report.user_action_detail() == _rendered_detail(_envelope(MODEL_NOT_ALLOWED_ERROR_CODE))
