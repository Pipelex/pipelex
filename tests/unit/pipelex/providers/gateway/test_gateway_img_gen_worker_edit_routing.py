"""Tests that img2img (input images present) calls route to /images/edits, not /images/generations.

Azure/OpenAI's Images API splits generation and editing across two REST routes, and only
/images/edits accepts the 'image' parameter — /images/generations rejects it with a 400
"Unknown parameter". The args factory maps input images to httpx-style file tuples under
"image"; the worker must send them as a multipart body. Because portkey_ai's
AsyncAPIClient never forwards 'files' to httpx, the worker routes that one call through
the vendored AsyncOpenAI client its AsyncPortkey already carries (scalar args travel as
`body` and are serialized to multipart form fields by the openai SDK).
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from portkey_ai.api_resources.utils import GenericResponse

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.providers.gateway.gateway_img_gen_worker import GatewayImgGenWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_PNG_FILE_TUPLE = ("image_0.png", _PNG_BYTES, "image/png")
_PNG_FILE_TUPLE_2 = ("image_1.png", _PNG_BYTES, "image/png")

# Production gateway config style: the explicit endpoint_path key on the model spec,
# with no leading slash (httpx's base_url merge makes the two forms equivalent).
_GENERATIONS_ENDPOINT_PATH = "openai/deployments/gpt-image-1-2025-04-15/images/generations?api-version=2025-04-01-preview"
_EDITS_ENDPOINT_PATH = "openai/deployments/gpt-image-1-2025-04-15/images/edits?api-version=2025-04-01-preview"


def _make_worker(mocker: MockerFixture, *, endpoint_path: str = _GENERATIONS_ENDPOINT_PATH) -> tuple[GatewayImgGenWorker, Any, Any]:
    """Build a worker with a mocked AsyncPortkey; return (worker, generations post mock, edits post mock)."""
    worker = object.__new__(GatewayImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.desc = "test-gateway-img-model"
    mock_model.extra_headers = {"endpoint_path": endpoint_path}
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_generations_post = mocker.AsyncMock()
    mock_options = mocker.MagicMock()
    mock_options.post = mock_generations_post
    mock_client = mocker.MagicMock()
    mock_client.with_options.return_value = mock_options
    mock_edits_post = mocker.AsyncMock()
    mock_client.openai_client.post = mock_edits_post
    worker.portkey_client = mock_client
    return worker, mock_generations_post, mock_edits_post


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "test prompt"
    job.job_report.img_gen_tokens_usage = None
    return job


def _patch_args(mocker: MockerFixture, *, args_dict: dict[str, Any]) -> None:
    mocker.patch(
        "pipelex.providers.gateway.gateway_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
        new_callable=mocker.AsyncMock,
        return_value=args_dict,
    )
    mocker.patch(
        "pipelex.providers.gateway.gateway_img_gen_worker.GatewayDeck.get_config_id",
        return_value="cfg-1",
    )


def _success_response_dict() -> dict[str, Any]:
    b64_json = base64.b64encode(_PNG_BYTES).decode("ascii")
    return {"data": [{"b64_json": b64_json}], "output_format": "png", "size": "1024x1024"}


def _make_edits_http_response(mocker: MockerFixture) -> Any:
    http_response = mocker.MagicMock()
    http_response.json.return_value = _success_response_dict()
    return http_response


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayImgGenWorkerEditRouting:
    """When 'image' is present in args_dict, the worker must post a multipart body to /images/edits via the vendored async openai client."""

    async def test_with_input_image_routes_to_edits_with_multipart_body(self, mocker: MockerFixture) -> None:
        worker, mock_generations_post, mock_edits_post = _make_worker(mocker)
        mock_edits_post.return_value = _make_edits_http_response(mocker)
        _patch_args(mocker, args_dict={"prompt": "edit me", "n": 1, "size": "1024x1024", "image": [_PNG_FILE_TUPLE]})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        # The edit call goes through the vendored AsyncOpenAI client the AsyncPortkey carries
        # (portkey_ai's AsyncAPIClient silently drops 'files'); the portkey post must not be used.
        mock_generations_post.assert_not_called()

        call = mock_edits_post.call_args
        assert call.args == (_EDITS_ENDPOINT_PATH,)
        assert call.kwargs["cast_to"] is httpx.Response
        # Scalars travel as `body` (raw, unstringified) — the openai SDK serializes them to
        # multipart form fields; the image is removed from the body and sent as a file part.
        assert call.kwargs["body"] == {"prompt": "edit me", "n": 1, "size": "1024x1024"}
        assert call.kwargs["files"] == [("image", _PNG_FILE_TUPLE)]
        headers = call.kwargs["options"]["headers"]
        assert headers["x-portkey-config"] == "cfg-1"
        assert headers["Content-Type"] == "multipart/form-data"

    async def test_with_multiple_input_images_sends_bracketed_array_field_name(self, mocker: MockerFixture) -> None:
        """Multiple input images must travel as 'image[]' parts (OpenAI multipart array convention);
        repeated bare 'image' parts are collapsed to one by the server, silently dropping the others.
        """
        worker, mock_generations_post, mock_edits_post = _make_worker(mocker)
        mock_edits_post.return_value = _make_edits_http_response(mocker)
        _patch_args(mocker, args_dict={"prompt": "edit me", "image": [_PNG_FILE_TUPLE, _PNG_FILE_TUPLE_2]})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        mock_generations_post.assert_not_called()
        multipart_files: list[tuple[str, Any]] = mock_edits_post.call_args.kwargs["files"]
        assert multipart_files == [("image[]", _PNG_FILE_TUPLE), ("image[]", _PNG_FILE_TUPLE_2)]
        assert all(field[0] != "image" for field in multipart_files)

    async def test_without_input_image_routes_to_generations_as_before(self, mocker: MockerFixture) -> None:
        worker, mock_generations_post, mock_edits_post = _make_worker(mocker)
        mock_generations_post.return_value = GenericResponse.model_validate(_success_response_dict())
        _patch_args(mocker, args_dict={"prompt": "generate me", "n": 1})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        mock_edits_post.assert_not_called()
        call_kwargs = mock_generations_post.call_args.kwargs
        assert call_kwargs["url"] == _GENERATIONS_ENDPOINT_PATH
        assert "files" not in call_kwargs
        assert call_kwargs["prompt"] == "generate me"
        assert call_kwargs["n"] == 1

    async def test_with_input_image_but_no_generations_segment_raises(self, mocker: MockerFixture) -> None:
        """A model whose endpoint doesn't follow the generations/edits split must fail loud, not silently mis-route."""
        worker, _, mock_edits_post = _make_worker(mocker, endpoint_path="/some/other/route")
        _patch_args(mocker, args_dict={"prompt": "edit me", "image": [_PNG_FILE_TUPLE]})

        with pytest.raises(ImgGenParameterError):
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        mock_edits_post.assert_not_called()
