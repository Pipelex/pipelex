"""Tests that img2img (input images present) calls route to /images/edits with multipart field
names following OpenAI's convention: a single file travels as the bare 'image' field, but multiple
files must each go under 'image[]' — repeated bare 'image' parts are collapsed to one by the
server, silently dropping the others.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest

from pipelex.providers.azure_rest.azure_img_gen_worker import AzureImgGenWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_PNG_FILE_TUPLE = ("image_0.png", _PNG_BYTES, "image/png")
_PNG_FILE_TUPLE_2 = ("image_1.png", _PNG_BYTES, "image/png")


def _make_worker(mocker: MockerFixture) -> AzureImgGenWorker:
    worker = object.__new__(AzureImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-azure-img-model"
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model
    worker.api_key = "test-key"
    worker.endpoint = "https://test.azure.com"
    worker.api_version = "2025-04-01-preview"
    worker.model_handle = mocker.MagicMock()
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "edit me"
    job.job_report.img_gen_tokens_usage = None
    return job


def _patch_httpx_success(mocker: MockerFixture, *, args_dict: dict[str, Any]) -> Any:
    """Patch the worker's httpx.AsyncClient with a successful GPT-Image-shaped response; return the client mock."""
    mock_client = mocker.MagicMock()
    mock_response = mocker.MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200
    mock_response.headers = httpx.Headers({})
    mock_response.json.return_value = {"output_format": "png", "data": [{"b64_json": "aGVsbG8="}], "size": "1024x1024"}
    mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
    mock_client.post = mocker.AsyncMock(return_value=mock_response)
    mocker.patch("pipelex.providers.azure_rest.azure_img_gen_worker.httpx.AsyncClient", return_value=mock_client)
    mocker.patch(
        "pipelex.providers.azure_rest.azure_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
        new_callable=mocker.AsyncMock,
        return_value=args_dict,
    )
    return mock_client


@pytest.mark.asyncio(loop_scope="class")
class TestAzureImgGenWorkerEditRouting:
    """When 'image' is present in args_dict, the worker must post multipart to /images/edits with correctly named parts."""

    async def test_single_input_image_routes_to_edits_with_bare_image_field(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        mock_client = _patch_httpx_success(mocker, args_dict={"quality": "medium", "image": [_PNG_FILE_TUPLE]})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        call_args = mock_client.post.call_args
        assert call_args.args[0] == "https://test.azure.com/openai/deployments/gpt-image-1/images/edits?api-version=2025-04-01-preview"
        assert call_args.kwargs["files"] == [("image", _PNG_FILE_TUPLE)]
        assert call_args.kwargs["data"] == {"quality": "medium", "prompt": "edit me"}

    async def test_multiple_input_images_send_bracketed_array_field_name(self, mocker: MockerFixture) -> None:
        """Multiple input images must travel as 'image[]' parts (OpenAI multipart array convention)."""
        worker = _make_worker(mocker)
        mock_client = _patch_httpx_success(mocker, args_dict={"image": [_PNG_FILE_TUPLE, _PNG_FILE_TUPLE_2]})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        files = mock_client.post.call_args.kwargs["files"]
        assert files == [("image[]", _PNG_FILE_TUPLE), ("image[]", _PNG_FILE_TUPLE_2)]

    async def test_without_input_image_routes_to_generations_with_json_body(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        mock_client = _patch_httpx_success(mocker, args_dict={"quality": "medium"})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        call_args = mock_client.post.call_args
        assert call_args.args[0] == "https://test.azure.com/openai/deployments/gpt-image-1/images/generations?api-version=2025-04-01-preview"
        assert "files" not in call_args.kwargs
        assert call_args.kwargs["json"] == {"quality": "medium", "prompt": "edit me"}
