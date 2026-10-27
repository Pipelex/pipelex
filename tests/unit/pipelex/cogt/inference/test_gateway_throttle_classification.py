from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

import httpx
import openai
import pytest
from mthds.protocol.problem.registry import CoreCode
from portkey_ai import Portkey
from portkey_ai._vendor import openai as portkey_vendored_openai

from pipelex.cogt.exceptions import InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind, extract_gateway_metadata, extract_openai_metadata
from pipelex.cogt.inference.error_classify import InferenceErrorFamily, classify_inference_error
from pipelex.cogt.inference.error_render import render_inference_error
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.errors.problem import ProblemView
from tests.unit.pipelex.cogt.test_data import GatewayThrottleTestData

if TYPE_CHECKING:
    from collections.abc import Callable

_ORIGIN = "https://gateway.example.com"


def _gateway_response(*, body: dict[str, Any], retry_after: str, extra_headers: dict[str, str] | None = None) -> tuple[httpx.Request, httpx.Response]:
    request = httpx.Request("POST", f"{_ORIGIN}/v1/images/generations")
    response = httpx.Response(
        status_code=429,
        request=request,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json", "retry-after": retry_after, **(extra_headers or {})},
    )
    return request, response


def _as_portkey_raises_it(*, body: dict[str, Any], retry_after: str, extra_headers: dict[str, str] | None = None) -> BaseException:
    """Build the exception through Portkey's own factory, which keeps only the message string on ``body``."""
    request, response = _gateway_response(body=body, retry_after=retry_after, extra_headers=extra_headers)
    client = Portkey(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1")
    return client._make_status_error_from_response(request=request, response=response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


def _as_portkey_s_vendored_openai_raises_it(*, body: dict[str, Any], retry_after: str, extra_headers: dict[str, str] | None = None) -> BaseException:
    """Build the exception through the OpenAI client Portkey vendors, the hop a gateway's image call takes.

    Its factory renders the whole body into the message and keeps the ``error`` section on ``body``, which is the
    shape of the refusal's diagnostics on the hosted API.
    """
    _, response = _gateway_response(body=body, retry_after=retry_after, extra_headers=extra_headers)
    client = portkey_vendored_openai.OpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1")
    return client._make_status_error_from_response(response)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


_HOPS = [
    pytest.param(_as_portkey_raises_it, id="portkey-factory"),
    pytest.param(_as_portkey_s_vendored_openai_raises_it, id="portkey-vendored-openai"),
]


class TestGatewayThrottleClassification:
    @pytest.mark.parametrize("raise_it", _HOPS)
    def test_azure_s_throttle_is_a_rate_limit_waited_for_the_delay_it_asks(self, raise_it: Callable[..., BaseException]) -> None:
        """Azure's refusal, verbatim, through each hop that raises a gateway's failure, is a retryable rate limit.

        The gateway's quota rule reads the status and the provider's code alone, so the message's link to Azure's
        quota-increase page decides nothing: the refusal is ``provider.rate_limited``, repeated within the run, and
        carries Azure's 57 seconds, where it used to fail at once as ``provider.quota_exhausted``.
        """
        exc = raise_it(body=GatewayThrottleTestData.AZURE_RATE_LIMIT_BODY, retry_after=GatewayThrottleTestData.AZURE_RETRY_AFTER)

        metadata = extract_gateway_metadata(exc)
        classification = classify_inference_error(metadata, family=InferenceErrorFamily.IMG_GEN)

        assert metadata.provider == ProviderName.GATEWAY
        assert metadata.status_code == 429
        assert metadata.provider_error_code == GatewayThrottleTestData.AZURE_RATE_LIMIT_CODE
        assert metadata.retry_after_seconds == 57
        assert "quota" in metadata.message
        assert metadata.is_quota_exhaustion is False
        assert classification.error_code == CoreCode.PROVIDER_RATE_LIMITED
        assert classification.category == InferenceErrorCategory.TRANSIENT
        assert classification.category.is_retryable is True
        assert classification.user_action_kind == UserActionKind.WAIT_AND_RETRY

        rendered = render_inference_error(
            metadata=metadata,
            classification=classification,
            family=InferenceErrorFamily.IMG_GEN,
            model_desc="gpt-image-2 → Model[gpt-image-2]",
            model_handle="gpt-image-2",
        )
        # As the worker's error enrichment does, which names the model and the backend the problem's sentence reads
        rendered.fill_model_and_provider("gpt-image-2", backend_name="pipelex_manifold")
        problem = rendered.to_problem(view=ProblemView.OPERATOR)

        assert problem.code == CoreCode.PROVIDER_RATE_LIMITED
        assert problem.is_retryable is True
        assert problem.retry_after == 57

    @pytest.mark.parametrize("raise_it", _HOPS)
    def test_azure_s_delay_in_milliseconds_is_read_before_its_seconds(self, raise_it: Callable[..., BaseException]) -> None:
        """Azure sends its delay twice, in milliseconds and in rounded seconds, and the milliseconds are the wait read."""
        exc = raise_it(
            body=GatewayThrottleTestData.AZURE_RATE_LIMIT_BODY,
            retry_after=GatewayThrottleTestData.AZURE_RETRY_AFTER,
            extra_headers={"retry-after-ms": GatewayThrottleTestData.AZURE_RETRY_AFTER_MS},
        )

        metadata = extract_gateway_metadata(exc)

        assert metadata.retry_after_seconds == GatewayThrottleTestData.AZURE_RETRY_AFTER_MS_SECONDS
        assert classify_inference_error(metadata, family=InferenceErrorFamily.IMG_GEN).error_code == CoreCode.PROVIDER_RATE_LIMITED

    @pytest.mark.parametrize("raise_it", _HOPS)
    def test_the_broad_quota_type_beside_another_code_reads_as_it_does_directly(self, raise_it: Callable[..., BaseException]) -> None:
        """OpenAI's broad quota `type` beside a code the set does not hold is a spent quota through a gateway, as it is directly.

        The gateway's Extract step keeps the code and the OpenAI one the type, so the rule reads both off the body. The
        code is built: one OpenAI's guide does not name.
        """
        body = copy.deepcopy(GatewayThrottleTestData.AZURE_RATE_LIMIT_BODY)
        body["error"]["type"] = GatewayThrottleTestData.OPENAI_QUOTA_CODE
        body["error"]["code"] = "quota_code_not_in_the_set"
        _, response = _gateway_response(body=body, retry_after=GatewayThrottleTestData.AZURE_RETRY_AFTER)
        direct_client = openai.OpenAI(api_key="unused-in-this-test", base_url=f"{_ORIGIN}/v1")
        direct_metadata = extract_openai_metadata(direct_client._make_status_error_from_response(response))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        gateway_metadata = extract_gateway_metadata(raise_it(body=body, retry_after=GatewayThrottleTestData.AZURE_RETRY_AFTER))

        assert gateway_metadata.provider_error_code == "quota_code_not_in_the_set"
        assert direct_metadata.provider_error_code == GatewayThrottleTestData.OPENAI_QUOTA_CODE
        for metadata in (gateway_metadata, direct_metadata):
            assert metadata.is_quota_exhaustion is True
            assert classify_inference_error(metadata, family=InferenceErrorFamily.IMG_GEN).error_code == CoreCode.PROVIDER_QUOTA_EXHAUSTED

    @pytest.mark.parametrize(
        ("error_type", "error_code"),
        [
            pytest.param(None, GatewayThrottleTestData.OPENAI_QUOTA_CODE, id="broad-code"),
            # OpenAI's billing shape: the cause in `code`, which the Extract step reads before the broad `type`
            pytest.param(
                GatewayThrottleTestData.OPENAI_QUOTA_CODE,
                GatewayThrottleTestData.OPENAI_CREDIT_BALANCE_EXHAUSTED_CODE,
                id="billing-code-beside-the-broad-type",
            ),
        ],
    )
    @pytest.mark.parametrize("raise_it", _HOPS)
    def test_the_same_refusal_on_openai_s_quota_code_is_a_spent_quota(
        self, raise_it: Callable[..., BaseException], error_type: str | None, error_code: str
    ) -> None:
        """The contrast: only the provider's code changes, and the code alone makes the 429 a spent quota."""
        body = copy.deepcopy(GatewayThrottleTestData.AZURE_RATE_LIMIT_BODY)
        body["error"]["type"] = error_type
        body["error"]["code"] = error_code
        exc = raise_it(body=body, retry_after=GatewayThrottleTestData.AZURE_RETRY_AFTER)

        metadata = extract_gateway_metadata(exc)
        classification = classify_inference_error(metadata, family=InferenceErrorFamily.IMG_GEN)

        assert metadata.provider_error_code == error_code
        assert metadata.is_quota_exhaustion is True
        assert classification.error_code == CoreCode.PROVIDER_QUOTA_EXHAUSTED
        assert classification.category == InferenceErrorCategory.CAPACITY
        assert classification.category.is_retryable is False
        assert classification.user_action_kind == UserActionKind.CHECK_BILLING
