"""Linkup bills by the request, so its workers record each call as one request priced at the model's rate.

The rates are per million tokens, so a request is recorded as a million tokens in and out, and the usage says it counts
requests. The event every inference call ends with keeps the request's cost and writes no token counts, which would
otherwise add a million tokens to a dashboard of tokens for every search. No provider is called: the SDK client is
mocked, so this needs no inference marker.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import pytest
from linkup import LinkupFetchResponse, LinkupSourcedAnswer
from pydantic import BaseModel

from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.inference.inference_call_summary import INFERENCE_CALL_ENDS_MESSAGE
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.pricing_unit import PricingUnit
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.providers.linkup.linkup_extract_worker import LinkupExtractWorker
from pipelex.providers.linkup.linkup_search_worker import LinkupSearchWorker
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.tools.log.log_fields import attached_field_names

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pytest_mock import MockerFixture

    from pipelex.cogt.usage.usage_cost import TokensUsage

SUMMARY_LOGGER = "pipelex.cogt.inference.inference_call_summary"
# Linkup's rate, per million tokens, which prices one request since a request is recorded as a million tokens.
REQUEST_RATE = 0.005
ONE_REQUEST = {TokenCategory.INPUT: 1_000_000, TokenCategory.OUTPUT: 1_000_000}


class CompanyBrief(BaseModel):
    name: str
    summary: str


def _model(*, model_type: ModelType, name: str, model_id: str, inputs: list[str], outputs: list[str]) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="linkup",
        name=name,
        sdk="linkup",
        model_type=model_type,
        model_id=model_id,
        inputs=inputs,
        outputs=outputs,
        costs={CostCategory.INPUT: REQUEST_RATE, CostCategory.OUTPUT: 0.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def _job_metadata() -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-linkup"),
        pipe_code="some_pipe",
    )


def _search_worker(mocker: MockerFixture, *, response: Any) -> LinkupSearchWorker:
    linkup_client = mocker.patch("pipelex.providers.linkup.linkup_search_worker.LinkupClient").return_value
    linkup_client.async_search = mocker.AsyncMock(return_value=response)
    model = _model(
        model_type=ModelType.SEARCH, name="linkup-standard", model_id="standard", inputs=["text"], outputs=["sourced-answers", "structured"]
    )
    return LinkupSearchWorker(inference_model=model, api_key="test-key")


async def _search_sourced_answer(mocker: MockerFixture) -> TokensUsage | None:
    worker = _search_worker(mocker, response=LinkupSourcedAnswer(answer="Acme makes anvils.", sources=[]))
    search_job = SearchJobFactory.make_search_job(
        "what does Acme make", search_setting=SearchSetting(model="linkup-standard"), job_metadata=_job_metadata()
    )
    await worker.search_sourced_answer(search_job=search_job)
    return search_job.job_report.search_tokens_usage


async def _search_structured(mocker: MockerFixture) -> TokensUsage | None:
    worker = _search_worker(mocker, response={"name": "Acme", "summary": "Acme makes anvils."})
    search_job = SearchJobFactory.make_search_job(
        "what does Acme make", search_setting=SearchSetting(model="linkup-standard"), job_metadata=_job_metadata()
    )
    await worker.search_structured(search_job=search_job, schema=CompanyBrief)
    return search_job.job_report.search_tokens_usage


async def _fetch_page(mocker: MockerFixture) -> TokensUsage | None:
    linkup_client = mocker.patch("pipelex.providers.linkup.linkup_extract_worker.LinkupClient").return_value
    linkup_client.async_fetch = mocker.AsyncMock(return_value=LinkupFetchResponse(markdown="# Acme"))
    model = _model(model_type=ModelType.TEXT_EXTRACTOR, name="linkup-fetch", model_id="fetch", inputs=["web_page"], outputs=["pages"])
    worker = LinkupExtractWorker(extra_config={}, inference_model=model, api_key="test-key")
    extract_job = ExtractJob(
        extract_input=ExtractInput(document_uri="https://example.com/acme"),
        job_params=ExtractJobParams.make_default_extract_job_params(),
        job_config=ExtractJobConfig(),
        job_report=ExtractJobReport(),
        job_metadata=_job_metadata(),
    )
    await worker.extract_pages(extract_job=extract_job)
    return extract_job.job_report.extract_tokens_usage


@pytest.mark.asyncio(loop_scope="class")
class TestLinkupRequestPricing:
    @pytest.mark.parametrize(
        "run_call",
        [_search_sourced_answer, _search_structured, _fetch_page],
        ids=["a sourced-answer search", "a structured search", "a page fetch"],
    )
    async def test_a_linkup_call_is_priced_as_one_request_and_its_event_writes_no_token_counts(
        self, caplog: pytest.LogCaptureFixture, mocker: MockerFixture, run_call: Callable[[MockerFixture], Awaitable[TokensUsage | None]]
    ) -> None:
        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            tokens_usage = await run_call(mocker)

        assert tokens_usage is not None
        assert tokens_usage.nb_tokens_by_category == ONE_REQUEST
        assert tokens_usage.pricing_unit is PricingUnit.REQUEST
        (record,) = [record for record in caplog.records if record.name == SUMMARY_LOGGER and record.getMessage() == INFERENCE_CALL_ENDS_MESSAGE]
        fields = {name: getattr(record, name) for name in attached_field_names(record=record)}
        assert fields["outcome"] == "success"
        assert math.isclose(fields["cost_usd"], REQUEST_RATE)
        assert GenAISpanAttr.USAGE_INPUT_TOKENS not in fields
        assert GenAISpanAttr.USAGE_OUTPUT_TOKENS not in fields
