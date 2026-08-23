"""Tests that img2img (input images present) calls route to /images/edits, not /images/generations.

OpenAI's Images API splits generation and editing across two routes, and only /images/edits
accepts input images — /images/generations rejects them with a 400 "Unknown parameter". The
worker picks the route by asking the SDK for the right method, and the SDK is also what decides
the multipart field names: a list under `image` is serialized as `image[]` parts, a single file
as the bare `image` field. That second distinction is a silent one to get wrong, which is why it
is asserted here rather than trusted.

Since the gateway routes on the model id in the request body, nothing in this path carries an
endpoint path or a config id any more: `model` travels in the body like every other argument.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import pytest
from portkey_ai.api_resources.types.image_type import ImagesResponse

from pipelex.providers.gateway.gateway_img_gen_worker import GatewayImgGenWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
_PNG_FILE_TUPLE = ("image_0.png", _PNG_BYTES, "image/png")
_PNG_FILE_TUPLE_2 = ("image_1.png", _PNG_BYTES, "image/png")


def _make_worker(mocker: MockerFixture) -> tuple[GatewayImgGenWorker, Any, Any]:
    """Build a worker with a mocked AsyncPortkey; return (worker, generate mock, edit mock)."""
    worker = object.__new__(GatewayImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.model_id = "gpt-image-1-2025-04-15"
    mock_model.name = "gpt-image-1"
    mock_model.desc = "test-gateway-img-model"
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_generate = mocker.AsyncMock()
    mock_edit = mocker.AsyncMock()
    mock_client = mocker.MagicMock()
    mock_client.images.generate = mock_generate
    mock_client.images.edit = mock_edit
    worker.portkey_client = mock_client
    return worker, mock_generate, mock_edit


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


def _success_response() -> ImagesResponse:
    b64_json = base64.b64encode(_PNG_BYTES).decode("ascii")
    return ImagesResponse.model_validate({"data": [{"b64_json": b64_json}], "output_format": "png", "size": "1024x1024"})


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayImgGenWorkerEditRouting:
    """When 'image' is present in args_dict, the worker must call images.edit; otherwise images.generate."""

    async def test_with_input_image_calls_edit_with_the_bare_image_field(self, mocker: MockerFixture) -> None:
        worker, mock_generate, mock_edit = _make_worker(mocker)
        mock_edit.return_value = _success_response()
        _patch_args(
            mocker,
            args_dict={"model": "gpt-image-1-2025-04-15", "prompt": "edit me", "n": 1, "size": "1024x1024", "image": [_PNG_FILE_TUPLE]},
        )

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        mock_generate.assert_not_called()
        call_kwargs = mock_edit.call_args.kwargs
        # One image is the file itself, not a list: that is what makes the SDK send a bare
        # `image` part rather than `image[]`.
        assert call_kwargs["image"] == _PNG_FILE_TUPLE
        # Everything else travels as it came out of the args factory, `model` included — the
        # gateway reads it from the body to decide where the request goes.
        assert call_kwargs["model"] == "gpt-image-1-2025-04-15"
        assert call_kwargs["prompt"] == "edit me"
        assert call_kwargs["n"] == 1
        assert call_kwargs["size"] == "1024x1024"

    async def test_with_multiple_input_images_passes_a_list_so_the_sdk_brackets_the_field(self, mocker: MockerFixture) -> None:
        """Multiple input images must travel as 'image[]' parts (OpenAI multipart array convention);
        repeated bare 'image' parts are collapsed to one by the server, silently dropping the others.
        The SDK derives that field name from the argument being a list, so the list is the contract.
        """
        worker, mock_generate, mock_edit = _make_worker(mocker)
        mock_edit.return_value = _success_response()
        _patch_args(mocker, args_dict={"model": "gpt-image-1-2025-04-15", "prompt": "edit me", "image": [_PNG_FILE_TUPLE, _PNG_FILE_TUPLE_2]})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        mock_generate.assert_not_called()
        assert mock_edit.call_args.kwargs["image"] == [_PNG_FILE_TUPLE, _PNG_FILE_TUPLE_2]

    async def test_without_input_image_calls_generate(self, mocker: MockerFixture) -> None:
        worker, mock_generate, mock_edit = _make_worker(mocker)
        mock_generate.return_value = _success_response()
        _patch_args(mocker, args_dict={"model": "gpt-image-1-2025-04-15", "prompt": "generate me", "n": 1})

        await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        mock_edit.assert_not_called()
        call_kwargs = mock_generate.call_args.kwargs
        assert "image" not in call_kwargs
        assert call_kwargs["model"] == "gpt-image-1-2025-04-15"
        assert call_kwargs["prompt"] == "generate me"
        assert call_kwargs["n"] == 1
