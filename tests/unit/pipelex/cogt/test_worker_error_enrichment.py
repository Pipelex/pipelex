"""Worker-level coverage for model/provider enrichment of inference-failure errors.

A `CogtError` raised deep inside a provider plugin (LLMCompletionError,
ImgGenGenerationError, ExtractJobFailureError, SearchJobFailureError) carries
no model or provider of its own. Each worker family's public-method chokepoint
fills `model_handle` / `backend_name` from the worker — where both are
unambiguously known — so the eventual `ErrorReport` can attribute the failure.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel
from typing_extensions import override

from pipelex.cogt.exceptions import (
    ExtractJobFailureError,
    ImgGenGenerationError,
    InferenceErrorCategory,
    LLMCompletionError,
    LLMModelNotFoundError,
    SearchJobFailureError,
)
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

WORKER_MODEL = "claude-sonnet-4"
WORKER_PROVIDER = "anthropic"


class _StubSchema(BaseModel):
    """Minimal schema for the gen_object code path."""


class _StubLLMWorker(LLMWorkerAbstract):
    """LLM worker whose abstract impl always raises the supplied error."""

    def __init__(self, model_handle: str, provider_name: str, error: Exception) -> None:
        LLMWorkerAbstract.__init__(self, reporting_delegate=None)
        self._model_handle = model_handle
        self._provider_name = provider_name
        self._error = error

    @property
    @override
    def is_gen_object_supported(self) -> bool:
        return True

    @property
    @override
    def is_vision_supported(self) -> bool:
        return True

    @override
    def _get_request_model_name(self) -> str:
        return self._model_handle

    @override
    def _get_provider_name(self) -> str:
        return self._provider_name

    @override
    async def _gen_text(self, llm_job: Any) -> str:
        raise self._error

    @override
    async def _gen_object(self, llm_job: Any, schema: Any) -> Any:
        raise self._error


class _StubImgGenWorker(ImgGenWorkerAbstract):
    """Img-gen worker whose abstract impl always raises the supplied error."""

    def __init__(self, inference_model: Any, error: Exception) -> None:
        ImgGenWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=None)
        self._error = error

    @override
    async def _gen_image(self, img_gen_job: Any) -> Any:
        raise self._error

    @override
    async def _gen_image_list(self, img_gen_job: Any, nb_images: int) -> Any:
        raise self._error


class _StubExtractWorker(ExtractWorkerAbstract):
    """Extract worker whose abstract impl always raises the supplied error."""

    def __init__(self, inference_model: Any, error: Exception) -> None:
        ExtractWorkerAbstract.__init__(self, extra_config={}, inference_model=inference_model, reporting_delegate=None)
        self._error = error

    @override
    async def _extract_pages(self, extract_job: Any) -> Any:
        raise self._error


class _StubSearchWorker(SearchWorkerAbstract):
    """Search worker whose abstract impl always raises the supplied error."""

    def __init__(self, inference_model: Any, error: Exception) -> None:
        SearchWorkerAbstract.__init__(self, inference_model=inference_model, reporting_delegate=None)
        self._error = error

    @override
    async def _search_sourced_answer(self, search_job: Any) -> Any:
        raise self._error

    @override
    async def _search_structured(self, search_job: Any, schema: Any) -> Any:
        raise self._error


def _make_llm_job(mocker: MockerFixture) -> Any:
    """LLM job with telemetry disabled so the OTel span is skipped."""
    job = mocker.MagicMock()
    job.job_metadata.otel_context = None
    return job


def _make_extract_job(mocker: MockerFixture) -> Any:
    """Extract job whose inputs make the capability check a no-op."""
    job = mocker.MagicMock()
    job.extract_input.image_uri = None
    job.extract_input.document_uri = None
    job.job_params.should_caption_images = False
    return job


def _make_inference_model() -> SimpleNamespace:
    """Stub inference model exposing the fields the workers read."""
    return SimpleNamespace(name=WORKER_MODEL, backend_name=WORKER_PROVIDER, tag="stub-tag", desc="stub-desc")


@pytest.mark.asyncio(loop_scope="class")
class TestWorkerErrorEnrichment:
    """Each worker family fills model/provider onto a CogtError at its chokepoint."""

    @pytest.mark.parametrize("use_object", [False, True])
    async def test_llm_worker_enriches_error(self, mocker: MockerFixture, use_object: bool) -> None:
        """gen_text / gen_object stamp the worker's model and provider onto a bare LLMCompletionError."""
        error = LLMCompletionError("LLM worker failed", error_category=InferenceErrorCategory.TRANSIENT)
        worker = _StubLLMWorker(model_handle=WORKER_MODEL, provider_name=WORKER_PROVIDER, error=error)
        job = _make_llm_job(mocker)
        invocation = worker.gen_object(llm_job=job, schema=_StubSchema) if use_object else worker.gen_text(llm_job=job)

        with pytest.raises(LLMCompletionError) as exc_info:
            await invocation

        report = exc_info.value.to_error_report()
        assert report.model == WORKER_MODEL
        assert report.provider == WORKER_PROVIDER

    async def test_llm_worker_does_not_overwrite_existing_model(self, mocker: MockerFixture) -> None:
        """An inner error that already set model_handle keeps its value; only the missing provider is filled."""
        inner_model = "preset-only-model"
        error = LLMModelNotFoundError("model not found", model_handle=inner_model)
        worker = _StubLLMWorker(model_handle=WORKER_MODEL, provider_name=WORKER_PROVIDER, error=error)

        with pytest.raises(LLMModelNotFoundError) as exc_info:
            await worker.gen_text(llm_job=_make_llm_job(mocker))

        report = exc_info.value.to_error_report()
        assert report.model == inner_model
        assert report.provider == WORKER_PROVIDER

    async def test_llm_worker_skips_unknown_provider(self, mocker: MockerFixture) -> None:
        """A worker that does not know its provider ('unknown' default) leaves provider unset."""
        error = LLMCompletionError("LLM worker failed", error_category=InferenceErrorCategory.TRANSIENT)
        worker = _StubLLMWorker(model_handle=WORKER_MODEL, provider_name="unknown", error=error)

        with pytest.raises(LLMCompletionError) as exc_info:
            await worker.gen_text(llm_job=_make_llm_job(mocker))

        report = exc_info.value.to_error_report()
        assert report.model == WORKER_MODEL
        assert report.provider is None

    @pytest.mark.parametrize("use_list", [False, True])
    async def test_img_gen_worker_enriches_error(self, mocker: MockerFixture, use_list: bool) -> None:
        """gen_image / gen_image_list stamp model and provider onto a bare ImgGenGenerationError."""
        error = ImgGenGenerationError("img-gen worker failed", error_category=InferenceErrorCategory.TRANSIENT)
        worker = _StubImgGenWorker(inference_model=_make_inference_model(), error=error)
        invocation = (
            worker.gen_image_list(img_gen_job=mocker.MagicMock(), nb_images=2) if use_list else worker.gen_image(img_gen_job=mocker.MagicMock())
        )

        with pytest.raises(ImgGenGenerationError) as exc_info:
            await invocation

        report = exc_info.value.to_error_report()
        assert report.model == WORKER_MODEL
        assert report.provider == WORKER_PROVIDER

    async def test_extract_worker_enriches_error(self, mocker: MockerFixture) -> None:
        """extract_pages stamps model and provider onto a bare ExtractJobFailureError."""
        error = ExtractJobFailureError("extract worker failed", error_category=InferenceErrorCategory.TRANSIENT)
        worker = _StubExtractWorker(inference_model=_make_inference_model(), error=error)

        with pytest.raises(ExtractJobFailureError) as exc_info:
            await worker.extract_pages(extract_job=_make_extract_job(mocker))

        report = exc_info.value.to_error_report()
        assert report.model == WORKER_MODEL
        assert report.provider == WORKER_PROVIDER

    @pytest.mark.parametrize("use_structured", [False, True])
    async def test_search_worker_enriches_error(self, mocker: MockerFixture, use_structured: bool) -> None:
        """search_sourced_answer / search_structured stamp model and provider onto a bare SearchJobFailureError."""
        error = SearchJobFailureError("search worker failed", error_category=InferenceErrorCategory.TRANSIENT)
        worker = _StubSearchWorker(inference_model=_make_inference_model(), error=error)
        invocation = (
            worker.search_structured(search_job=mocker.MagicMock(), schema=_StubSchema)
            if use_structured
            else worker.search_sourced_answer(search_job=mocker.MagicMock())
        )

        with pytest.raises(SearchJobFailureError) as exc_info:
            await invocation

        report = exc_info.value.to_error_report()
        assert report.model == WORKER_MODEL
        assert report.provider == WORKER_PROVIDER
