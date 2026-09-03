"""The request the native-route client actually builds, and the two ways a 2xx can still be wrong.

`POST /v1/pipelex/extract` and `POST /v1/pipelex/search` are not OpenAI-shaped, so they are called
with plain `httpx`. Building the request by hand is what makes the dialect's two properties readable
in a test rather than dependent on a vendor constructor's defaults: the only header about us is the
service token, and the body carries the model with nothing about routing.

The failure arm is the other half. A 2xx whose body is not JSON — an intermediary's HTML error page
is how this happens — left raw is neither a `PipelexError` nor annotated with the model, so it
escapes the Temporal error bridge (`convert_pipelex_errors`), gets marked retryable, and re-bills a
call that already reached a provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.inference.error_render import InferenceErrorFamily
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.providers.manifold.manifold_exceptions import ManifoldError
from pipelex.providers.manifold.manifold_native_client import ManifoldNativeClient

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_ORIGIN = "https://manifold.example.com"
_TOKEN = "manifold-service-token"


def _client() -> ManifoldNativeClient:
    return ManifoldNativeClient(backend=InferenceBackend(name="pipelex_manifold", endpoint=_ORIGIN, api_key=_TOKEN))


def _inference_model(mocker: MockerFixture) -> Any:
    model = mocker.MagicMock()
    model.name = "linkup-sourced-answer"
    model.desc = "test-manifold-search"
    return model


def _patch_transport(mocker: MockerFixture, response: httpx.Response) -> Any:
    """Stand in for the network at the `httpx.AsyncClient.post` seam.

    Patching the SDK's own method rather than the whole client keeps `raise_for_status` and the JSON
    decoding — the two things these tests are about — running for real.
    """
    return mocker.patch.object(httpx.AsyncClient, "post", new_callable=mocker.AsyncMock, return_value=response)


def _response(*, status_code: int = 200, json_body: Any = None, text_body: str | None = None) -> httpx.Response:
    request = httpx.Request("POST", f"{_ORIGIN}/v1/pipelex/search")
    if text_body is not None:
        return httpx.Response(status_code=status_code, request=request, text=text_body)
    return httpx.Response(status_code=status_code, request=request, json=json_body)


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldNativeClientRequest:
    async def test_the_wire_carries_one_token_header_and_a_body_with_no_routing(self, mocker: MockerFixture) -> None:
        post = _patch_transport(mocker, _response(json_body={"answer": "ok"}))

        await _client().post_json(
            route="/pipelex/search",
            body={"model": "linkup/standard", "query": "what is a manifold"},
            family=InferenceErrorFamily.SEARCH,
            inference_model=_inference_model(mocker),
        )

        assert post.call_args.args[0] == f"{_ORIGIN}/v1/pipelex/search"
        headers = post.call_args.kwargs["headers"]
        # Asserted whole: a header added later should turn this red rather than widen silently.
        assert headers == {"x-pipelex-api-key": _TOKEN, "Content-Type": "application/json"}
        assert post.call_args.kwargs["json"] == {"model": "linkup/standard", "query": "what is a manifold"}

    async def test_a_json_object_body_comes_back_as_a_dict(self, mocker: MockerFixture) -> None:
        _patch_transport(mocker, _response(json_body={"answer": "ok", "sources": []}))

        result = await _client().post_json(
            route="/pipelex/search",
            body={"model": "linkup/standard", "query": "q"},
            family=InferenceErrorFamily.SEARCH,
            inference_model=_inference_model(mocker),
        )

        assert result == {"answer": "ok", "sources": []}


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldNativeClientFailures:
    async def test_a_non_json_2xx_becomes_a_pipelex_error_naming_the_model(self, mocker: MockerFixture) -> None:
        _patch_transport(mocker, _response(text_body="<html><body>502 Bad Gateway</body></html>"))

        with pytest.raises(ManifoldError) as exc_info:
            await _client().post_json(
                route="/pipelex/search",
                body={"model": "linkup/standard", "query": "q"},
                family=InferenceErrorFamily.SEARCH,
                inference_model=_inference_model(mocker),
            )

        assert "linkup-sourced-answer" in exc_info.value.message

    async def test_a_2xx_carrying_a_json_scalar_is_refused_with_what_it_was(self, mocker: MockerFixture) -> None:
        _patch_transport(mocker, _response(json_body=["not", "an", "object"]))

        with pytest.raises(ManifoldError, match="list"):
            await _client().post_json(
                route="/pipelex/search",
                body={"model": "linkup/standard", "query": "q"},
                family=InferenceErrorFamily.SEARCH,
                inference_model=_inference_model(mocker),
            )

    async def test_a_status_error_is_classified_rather_than_raised_raw(self, mocker: MockerFixture) -> None:
        _patch_transport(mocker, _response(status_code=401, json_body={"error": {"message": "bad token"}}))

        with pytest.raises(CogtError):
            await _client().post_json(
                route="/pipelex/search",
                body={"model": "linkup/standard", "query": "q"},
                family=InferenceErrorFamily.SEARCH,
                inference_model=_inference_model(mocker),
            )
