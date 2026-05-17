"""Tests that a malformed Gateway success body surfaces as a categorized
ImgGenGenerationError, not a raw ValueError / binascii.Error / PIL error.

The HTTP request succeeds here — it is the *body* parsing that fails. A raw
exception escaping at this point would slip past the Temporal PipelexError
bridge (``convert_pipelex_errors``), get marked retryable, and resubmit the
non-idempotent image generation — double-billing the user.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import pytest
from portkey_ai.api_resources.utils import GenericResponse

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.plugins.gateway.gateway_img_gen_worker import GatewayImgGenWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# Valid base64 that decodes to a PNG magic header followed by garbage: file-type
# detection recognizes it as a PNG, but PIL cannot open it (raises OSError).
_PNG_HEADER_GARBAGE = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40).decode("ascii")

# Valid base64 that decodes to bytes with no recognizable file signature: file-type
# detection cannot identify it and raises FileTypeError (a PipelexError, not a
# ValueError/OSError) — so it must be in the wrapper's except clause too.
_UNRECOGNIZED_BYTES = base64.b64encode(b"plainly not an image" + b"\x00" * 40).decode("ascii")


def _make_worker(mocker: MockerFixture) -> GatewayImgGenWorker:
    worker = object.__new__(GatewayImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.model_id = "gpt-image-1"
    mock_model.name = "gpt-image-1"
    mock_model.desc = "test-gateway-img-model"
    mock_model.extra_headers = {}
    mock_model.rules = mocker.MagicMock()
    worker.inference_model = mock_model

    mock_post = mocker.AsyncMock()
    mock_options = mocker.MagicMock()
    mock_options.post = mock_post
    mock_client = mocker.MagicMock()
    mock_client.with_options.return_value = mock_options
    worker.portkey_client = mock_client
    return worker


def _make_img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.positive_text = "test prompt"
    job.job_report.img_gen_tokens_usage = None
    return job


def _patch_gateway_success(mocker: MockerFixture, worker: GatewayImgGenWorker, response: GenericResponse) -> None:
    """Patch the worker so ``.post()`` succeeds and returns the given GenericResponse body."""
    worker.portkey_client.with_options.return_value.post.return_value = response  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    mocker.patch(
        "pipelex.plugins.gateway.gateway_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
        new_callable=mocker.AsyncMock,
        return_value={"prompt": "test"},
    )
    mocker.patch(
        "pipelex.plugins.gateway.gateway_img_gen_worker.GatewayDeck.get_config_id",
        return_value="cfg-1",
    )


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayImgGenWorkerMalformedBody:
    """A malformed success body is wrapped in a categorized ImgGenGenerationError."""

    @pytest.mark.parametrize("malformed_size", ["axb", "1024xfoo", "wide x tall"])
    async def test_gpt_image_malformed_size_is_wrapped(self, mocker: MockerFixture, malformed_size: str) -> None:
        """An Azure-GPT-Image body whose ``size`` has non-numeric dimensions must surface as a
        categorized ImgGenGenerationError, not a raw ValueError escaping the ``int()`` parse.
        """
        worker = _make_worker(mocker)
        # model_validate keeps the Azure-GPT-Image extras (size / output_format) — the
        # GenericResponse constructor does not declare them.
        response = GenericResponse.model_validate(
            {
                "success": True,
                "data": [{"b64_json": "aGVsbG8="}],
                "size": malformed_size,
                "output_format": "png",
            },
        )
        _patch_gateway_success(mocker, worker, response)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.UNKNOWN
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert "non-numeric" in exc_info.value.message

    @pytest.mark.parametrize(
        "malformed_base64",
        ["abc", _PNG_HEADER_GARBAGE, _UNRECOGNIZED_BYTES],
        ids=["invalid-base64-padding", "corrupt-image-bytes", "unrecognized-file-type"],
    )
    async def test_flux_2_pro_undecodable_image_is_wrapped(self, mocker: MockerFixture, malformed_base64: str) -> None:
        """A Flux-2-Pro body carrying invalid base64, undecodable image bytes, or bytes with no
        recognizable file signature must surface as a categorized ImgGenGenerationError, not a raw
        binascii.Error / PIL OSError / FileTypeError. The body omits ``size``/``output_format`` so
        GPT-Image validation fails and the Flux-2-Pro branch is taken.
        """
        worker = _make_worker(mocker)
        response = GenericResponse.model_validate({"success": True, "data": [{"b64_json": malformed_base64}]})
        _patch_gateway_success(mocker, worker, response)

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await worker._gen_image_list(img_gen_job=_make_img_gen_job(mocker), nb_images=1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.error_category is InferenceErrorCategory.UNKNOWN
        assert exc_info.value.user_action is not None
        assert exc_info.value.user_action.kind is UserActionKind.CHANGE_MODEL
        assert "decode" in exc_info.value.message
