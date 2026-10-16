from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from google import genai
from google.genai import types as genai_types
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.cogt.img_gen.img_gen_gemini_mapping import ResolvedGeminiImageConfig
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy, ImgGenArgTopic
from pipelex.cogt.inference.error_classification import UserActionKind
from pipelex.cogt.llm import completion_stop
from pipelex.providers.google.google_img_gen_worker import GoogleImgGenWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_MODEL_HANDLE = "nano-banana"
_MODEL_ID = "gemini-2.5-flash-image"
_IMAGE_BYTES = b"\x89PNG\r\n\x1a\nnot-really-a-png"
_USAGE: dict[str, Any] = {"promptTokenCount": 9, "totalTokenCount": 9}

# Gemini's answers on the wire, as its API sends them: a 200 whatever happened to the image.


def _finished_without_image(finish_reason: str) -> dict[str, Any]:
    """A candidate the model stopped for the reason given, holding no content."""
    return {"candidates": [{"finishReason": finish_reason, "index": 0}], "usageMetadata": _USAGE, "modelVersion": _MODEL_ID}


def _blocked_prompt(block_reason: str) -> dict[str, Any]:
    """No candidate at all: the prompt was blocked before the model wrote anything, its reason in the prompt feedback."""
    return {"promptFeedback": {"blockReason": block_reason}, "usageMetadata": _USAGE, "modelVersion": _MODEL_ID}


_NO_CANDIDATE_AND_NO_FEEDBACK: dict[str, Any] = {"usageMetadata": _USAGE, "modelVersion": _MODEL_ID}

_GENERATED_IMAGE: dict[str, Any] = {
    "candidates": [
        {
            "content": {"role": "model", "parts": [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(_IMAGE_BYTES).decode()}}]},
            "finishReason": "STOP",
            "index": 0,
        }
    ],
    "usageMetadata": _USAGE,
    "modelVersion": _MODEL_ID,
}


def _worker(mocker: MockerFixture, *, http_client: httpx.AsyncClient) -> GoogleImgGenWorker:
    """A worker over a real genai client, whose every request Gemini answers through the HTTP client given."""
    worker = object.__new__(GoogleImgGenWorker)
    inference_model = mocker.MagicMock()
    inference_model.desc = f"{_MODEL_HANDLE} → Model[{_MODEL_ID}]"
    inference_model.model_id = _MODEL_ID
    inference_model.name = _MODEL_HANDLE
    inference_model.rules = {ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GEMINI_3_FLASH}
    worker.inference_model = inference_model
    client = genai.Client(api_key="unused-in-this-test", http_options=genai_types.HttpOptions(httpx_async_client=http_client))
    worker.genai_async_client = client.aio
    mocker.patch(
        "pipelex.providers.google.google_img_gen_worker.ImgGenGeminiMapping.resolve_image_config",
        return_value=ResolvedGeminiImageConfig(aspect_ratio="1:1", image_size=None, width=1024, height=1024),
    )
    return worker


def _answering(body: dict[str, Any]) -> httpx.AsyncClient:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json=body, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


def _img_gen_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.job_params.aspect_ratio = None
    job.job_params.size = None
    job.img_gen_prompt.positive_text = "a cute cat"
    job.img_gen_prompt.input_images = None
    job.job_report.img_gen_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleImgGenWorkerRefusal:
    @pytest.mark.parametrize(
        ("answer", "reason"),
        [
            (_finished_without_image("IMAGE_SAFETY"), "IMAGE_SAFETY"),
            (_finished_without_image("IMAGE_PROHIBITED_CONTENT"), "IMAGE_PROHIBITED_CONTENT"),
            (_finished_without_image("SAFETY"), "SAFETY"),
            (_blocked_prompt("PROHIBITED_CONTENT"), "PROHIBITED_CONTENT"),
            (_blocked_prompt("IMAGE_SAFETY"), "IMAGE_SAFETY"),
        ],
    )
    async def test_a_safety_block_reads_content_refused(self, mocker: MockerFixture, answer: dict[str, Any], reason: str) -> None:
        """A finish or block reason naming a filter is the caller's input refused, not an empty answer."""
        async with _answering(answer) as http_client:
            worker = _worker(mocker, http_client=http_client)
            with pytest.raises(ImgGenGenerationError) as exc_info:
                await worker._gen_image(img_gen_job=_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        error = exc_info.value
        assert error.resolve_error_code() == CoreCode.MODEL_CONTENT_REFUSED
        assert error.error_category is InferenceErrorCategory.CONTENT
        assert error.user_action is not None
        assert error.user_action.kind is UserActionKind.CHANGE_INPUT
        assert f"'{reason}'" in error.message
        assert f"'{_MODEL_HANDLE}'" in error.message
        assert _MODEL_ID not in error.message
        report = error.to_error_report()
        assert report.code == CoreCode.MODEL_CONTENT_REFUSED
        assert report.error_domain == ErrorDomain.INPUT
        assert report.http_status == 422
        assert report.caller_facing_message is True

    @pytest.mark.parametrize(
        "answer",
        [
            # The model was asked for an image and made none, for no reason a filter gave
            _finished_without_image("NO_IMAGE"),
            _finished_without_image("IMAGE_OTHER"),
            _NO_CANDIDATE_AND_NO_FEEDBACK,
        ],
    )
    async def test_an_empty_answer_with_no_refusal_stays_unusable(self, mocker: MockerFixture, answer: dict[str, Any]) -> None:
        async with _answering(answer) as http_client:
            worker = _worker(mocker, http_client=http_client)
            with pytest.raises(ImgGenGenerationError) as exc_info:
                await worker._gen_image(img_gen_job=_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.resolve_error_code() == CoreCode.PROVIDER_RESPONSE_INVALID

    # genai warns that it does not know the value, and keeps it
    @pytest.mark.filterwarnings("ignore:IMAGE_BRAND_NEW is not a valid FinishReason")
    async def test_an_unknown_finish_reason_is_logged_as_an_image_generations(self, mocker: MockerFixture) -> None:
        """A value Gemini adds later is taken as normal and logged as an image generation's, never as an LLM's stop reason."""
        warning = mocker.patch.object(completion_stop.log, "warning")
        async with _answering(_finished_without_image("IMAGE_BRAND_NEW")) as http_client:
            worker = _worker(mocker, http_client=http_client)
            with pytest.raises(ImgGenGenerationError) as exc_info:
                await worker._gen_image(img_gen_job=_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert exc_info.value.resolve_error_code() == CoreCode.PROVIDER_RESPONSE_INVALID
        warning.assert_called_once_with(
            "An image finish reason was not recognized, so it was taken as normal",
            fields={"model_handle": _MODEL_HANDLE, "finish_reason": "IMAGE_BRAND_NEW"},
        )

    async def test_a_generated_image_is_returned(self, mocker: MockerFixture) -> None:
        async with _answering(_GENERATED_IMAGE) as http_client:
            worker = _worker(mocker, http_client=http_client)
            generated = await worker._gen_image(img_gen_job=_img_gen_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert generated.actual_bytes == _IMAGE_BYTES
        assert generated.mime_type == "image/png"
