"""Capture-stage tests for the extract token-usage path.

Extraction usage is either set by the provider inside ``_extract_pages`` or, when
the provider reports none, filled by the page-count fallback in
``ExtractWorkerAbstract.extract_pages`` (one "page" priced as 1,000,000 input +
1,000,000 output tokens). Neither branch is asserted anywhere today — extract
usage is uncovered in every mode. These tests pin both directions with a fake
in-process worker, no provider SDK required.
"""

from __future__ import annotations

import pytest
from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.pipeline.job_metadata import JobMetadata

_PER_PAGE_TOKENS = 1_000_000


class _FakeExtractWorker(ExtractWorkerAbstract):
    """Extract worker whose ``_extract_pages`` returns canned pages and optionally sets usage."""

    def __init__(self, inference_model: InferenceModelSpec, nb_pages: int, usage_to_set: NbTokensByCategoryDict | None) -> None:
        super().__init__(extra_config={}, inference_model=inference_model)
        self._nb_pages = nb_pages
        self._usage_to_set = usage_to_set

    @override
    async def _extract_pages(self, extract_job: ExtractJob) -> ExtractOutput:
        if self._usage_to_set is not None and (usage := extract_job.job_report.extract_tokens_usage):
            usage.nb_tokens_by_category = self._usage_to_set
        return ExtractOutput(pages={index: Page(text="page text") for index in range(self._nb_pages)})


def _make_extract_model() -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="test",
        name="test-extract",
        sdk="test_extract",
        model_type=ModelType.TEXT_EXTRACTOR,
        model_id="test-extract-id",
        inputs=["pdf"],
        outputs=["text"],
        costs={CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 1.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def _make_extract_job() -> ExtractJob:
    return ExtractJob(
        extract_input=ExtractInput(document_uri="/tmp/test.pdf"),  # noqa: S108
        job_params=ExtractJobParams.make_default_extract_job_params(),
        job_config=ExtractJobConfig(),
        job_report=ExtractJobReport(),
        job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="test-run"),
    )


class TestExtractWorkerUsageCapture:
    """Extract usage is provider-set when reported, else filled by the page-count fallback."""

    @pytest.mark.asyncio
    async def test_page_count_fallback_fills_usage_when_provider_reports_none(self) -> None:
        worker = _FakeExtractWorker(_make_extract_model(), nb_pages=3, usage_to_set=None)
        job = _make_extract_job()

        await worker.extract_pages(extract_job=job)

        captured = job.job_report.extract_tokens_usage
        assert captured is not None
        assert captured.nb_tokens_by_category == {
            TokenCategory.INPUT: 3 * _PER_PAGE_TOKENS,
            TokenCategory.OUTPUT: 3 * _PER_PAGE_TOKENS,
        }

    @pytest.mark.asyncio
    async def test_provider_reported_usage_is_not_overridden_by_fallback(self) -> None:
        provider_usage: NbTokensByCategoryDict = {TokenCategory.INPUT: 42, TokenCategory.OUTPUT: 7}
        worker = _FakeExtractWorker(_make_extract_model(), nb_pages=3, usage_to_set=provider_usage)
        job = _make_extract_job()

        await worker.extract_pages(extract_job=job)

        captured = job.job_report.extract_tokens_usage
        assert captured is not None
        assert captured.nb_tokens_by_category == provider_usage
