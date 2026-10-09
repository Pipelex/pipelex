from __future__ import annotations

import io
import json
import logging
import math
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from typing_extensions import override

from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.layout_tree import LayoutDocument, MarkdownBlock
from pipelex.cogt.doc_gen.render_job import RenderJob
from pipelex.cogt.exceptions import LLMCompletionError, SearchJobFailureError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job_factory import ImgGenJobFactory
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract
from pipelex.cogt.inference.inference_call_summary import INFERENCE_CALL_ENDS_MESSAGE, InferenceOperation
from pipelex.cogt.judgment.judgment_models import JudgmentAnswer, YesNoAnswer, YesNoQuestion
from pipelex.cogt.judgment.judgment_worker_abstract import JudgmentWorkerAbstract
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.search.search_worker_abstract import SearchWorkerAbstract
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.cogt.usage.usage_cost import compute_tokens_usage_cost
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.console_layouts import LogLayout
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log_fields import LAYOUT_MARK, attached_field_names
from tests.helpers.console_log_rendering import rendered_text
from tests.unit.pipelex.cogt.judgment.fake_judgment_worker import make_fake_judgment_job
from tests.unit.pipelex.providers.reportlab.reportlab_test_helpers import StubRenderResources, get_test_renderer

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pytest_mock import MockerFixture

    from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
    from pipelex.cogt.judgment.judgment_job import JudgmentJob
    from pipelex.cogt.search.search_job import SearchJob
    from pipelex.cogt.usage.usage_cost import TokensUsage
    from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar

SUMMARY_LOGGER = "pipelex.cogt.inference.inference_call_summary"
LLM_USAGE: NbTokensByCategoryDict = {TokenCategory.INPUT: 1200, TokenCategory.OUTPUT: 300}
OTHER_USAGE: NbTokensByCategoryDict = {TokenCategory.INPUT: 40, TokenCategory.OUTPUT: 8}
# The rates per million tokens every stand-in model is priced at: $1 in and $2 out.
RATES = {CostCategory.INPUT: 1.0, CostCategory.OUTPUT: 2.0}
STARTED_AT = 10.0
ENDED_AT = 11.25
DURATION_MS = 1250.0
RUN_TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF
PIPE_SPAN_ID = 0x00000000000000AB


def _model(
    *, model_type: ModelType, name: str, model_id: str, costs: dict[CostCategory, float] | None = None, inputs: list[str] | None = None
) -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="stand_in_backend",
        name=name,
        sdk="stand_in_sdk",
        model_type=model_type,
        model_id=model_id,
        inputs=inputs or ["text"],
        outputs=["text", "structured"],
        costs=RATES if costs is None else costs,
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def _job_metadata(*, otel_context: OtelContext | None = None) -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-summary"),
        pipe_code="some_pipe",
        otel_context=otel_context,
    )


def _record_usage(*, tokens_usage: TokensUsage | None, usage: NbTokensByCategoryDict | None) -> None:
    """What a provider's half of a worker does with the usage the provider answered with."""
    if tokens_usage is not None and usage is not None:
        tokens_usage.nb_tokens_by_category = dict(usage)


class _StandInLLMWorker(LLMWorkerAbstract):
    def __init__(self, *, usage: NbTokensByCategoryDict | None = None, error: Exception | None = None, reporting_delegate: Any = None) -> None:
        LLMWorkerAbstract.__init__(
            self, inference_model=_model(model_type=ModelType.LLM, name="gpt-test", model_id="gpt-test-2026"), reporting_delegate=reporting_delegate
        )
        self._usage = usage
        self._error = error

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        _record_usage(tokens_usage=llm_job.job_report.llm_tokens_usage, usage=self._usage)
        if self._error is not None:
            raise self._error
        return "answer"

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        raise NotImplementedError


class _StandInImgGenWorker(ImgGenWorkerAbstract):
    def __init__(self) -> None:
        ImgGenWorkerAbstract.__init__(self, inference_model=_model(model_type=ModelType.IMG_GEN, name="img-test", model_id="img-test-2026"))

    @override
    async def _gen_image(self, img_gen_job: ImgGenJob) -> GeneratedImageRawDetails:
        _record_usage(tokens_usage=img_gen_job.job_report.img_gen_tokens_usage, usage=OTHER_USAGE)
        return GeneratedImageRawDetails(size=None, actual_url="https://example.com/image.png")

    @override
    async def _gen_image_list(self, img_gen_job: ImgGenJob, *, nb_images: int) -> list[GeneratedImageRawDetails]:
        raise NotImplementedError


class _StandInExtractWorker(ExtractWorkerAbstract):
    def __init__(self, *, usage: NbTokensByCategoryDict | None) -> None:
        ExtractWorkerAbstract.__init__(
            self,
            extra_config={},
            inference_model=_model(model_type=ModelType.TEXT_EXTRACTOR, name="extract-test", model_id="extract-test-2026", inputs=["pdf"]),
        )
        self._usage = usage

    @override
    async def _extract_pages(self, extract_job: ExtractJob) -> ExtractOutput:
        _record_usage(tokens_usage=extract_job.job_report.extract_tokens_usage, usage=self._usage)
        return ExtractOutput(pages={index: Page(text="page text") for index in range(3)})


class _StandInSearchWorker(SearchWorkerAbstract):
    def __init__(self, *, error: Exception | None = None) -> None:
        SearchWorkerAbstract.__init__(self, inference_model=_model(model_type=ModelType.SEARCH, name="search-test", model_id="search-test-2026"))
        self._error = error

    @override
    async def _search_sourced_answer(self, search_job: SearchJob) -> SearchResultContent:
        _record_usage(tokens_usage=search_job.job_report.search_tokens_usage, usage=OTHER_USAGE)
        if self._error is not None:
            raise self._error
        return SearchResultContent(answer="an answer")

    @override
    async def _search_structured(self, search_job: SearchJob, *, schema: type[BaseModelTypeVar]) -> dict[str, Any]:
        raise NotImplementedError


class _StandInJudgmentWorker(JudgmentWorkerAbstract):
    def __init__(self) -> None:
        JudgmentWorkerAbstract.__init__(self, inference_model=_model(model_type=ModelType.JUDGMENT, name="judge-test", model_id="judge-test-2026"))

    @override
    async def _judge(self, judgment_job: JudgmentJob) -> dict[str, JudgmentAnswer]:
        _record_usage(tokens_usage=judgment_job.job_report.judgment_tokens_usage, usage=OTHER_USAGE)
        return {"is_urgent": YesNoAnswer(yes_no=True)}


def _llm_job(*, otel_context: OtelContext | None = None) -> LLMJob:
    return LLMJob(
        job_metadata=_job_metadata(otel_context=otel_context),
        llm_prompt=LLMPrompt(user_text="hello"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def _extract_job() -> ExtractJob:
    return ExtractJob(
        extract_input=ExtractInput(document_uri="https://example.com/report.pdf"),
        job_params=ExtractJobParams.make_default_extract_job_params(),
        job_config=ExtractJobConfig(),
        job_report=ExtractJobReport(),
        job_metadata=_job_metadata(),
    )


def _search_job() -> SearchJob:
    return SearchJobFactory.make_search_job("what is new", search_setting=SearchSetting(model="search-test"), job_metadata=_job_metadata())


async def _run_img_gen() -> None:
    img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt_contents("a cat", negative_text=None, job_metadata=_job_metadata())
    await _StandInImgGenWorker().gen_image(img_gen_job=img_gen_job)


async def _run_extract() -> None:
    await _StandInExtractWorker(usage=OTHER_USAGE).extract_pages(extract_job=_extract_job())


async def _run_search() -> None:
    await _StandInSearchWorker().search_sourced_answer(search_job=_search_job())


async def _run_judgment() -> None:
    await _StandInJudgmentWorker().judge(judgment_job=make_fake_judgment_job({"is_urgent": YesNoQuestion(instructions="Is it urgent?")}))


# Each family's call, its operation and its model keys. Each reports 40 tokens in and 8 out, which the stand-ins' rates
# price at $0.000056.
OTHER_TOKEN_FIELDS: dict[str, Any] = {GenAISpanAttr.USAGE_INPUT_TOKENS: 40, GenAISpanAttr.USAGE_OUTPUT_TOKENS: 8}
OTHER_COST_USD = 0.000056
FAMILY_CASES: list[tuple[Callable[[], Awaitable[None]], InferenceOperation, tuple[str, str]]] = [
    (_run_img_gen, InferenceOperation.IMG_GEN, ("img-test", "img-test-2026")),
    (_run_extract, InferenceOperation.EXTRACT, ("extract-test", "extract-test-2026")),
    (_run_search, InferenceOperation.SEARCH, ("search-test", "search-test-2026")),
    (_run_judgment, InferenceOperation.JUDGMENT, ("judge-test", "judge-test-2026")),
]
FAMILY_IDS = ["image generation", "extraction", "search", "judgment"]


def _summaries(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == SUMMARY_LOGGER and record.getMessage() == INFERENCE_CALL_ENDS_MESSAGE]


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields the call attached to the record, read the way a sink reads them."""
    return {name: getattr(record, name) for name in attached_field_names(record=record)}


@pytest.fixture
def fixed_clock(mocker: MockerFixture) -> None:
    """Every call starts at the same reading and ends 1.25 s later, so its duration is known."""
    mocker.patch("pipelex.cogt.inference.inference_call_summary.start_clock", return_value=STARTED_AT)
    mocker.patch("pipelex.tools.log.summary_fields.perf_counter", return_value=ENDED_AT)


@pytest.fixture
def span_exporter(mocker: MockerFixture) -> InMemorySpanExporter:
    """The runtime's tracer, replaced by one exporting to memory, so the test reads back the span the worker started."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer(__name__))
    return exporter


@pytest.mark.usefixtures("fixed_clock")
class TestInferenceCallSummary:
    @pytest.mark.asyncio
    async def test_a_successful_call_ends_with_the_event_and_the_usage_the_reporting_path_is_handed(
        self, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
    ) -> None:
        reporting_delegate = mocker.MagicMock()
        worker = _StandInLLMWorker(usage=LLM_USAGE, reporting_delegate=reporting_delegate)

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await worker.gen_text(llm_job=_llm_job())

        (record,) = _summaries(caplog)
        reported_job: LLMJob = reporting_delegate.report_inference_job.call_args.kwargs["inference_job"]
        reported_usage = reported_job.job_report.llm_tokens_usage
        assert reported_usage is not None
        assert record.levelno == logging.INFO
        assert record.__dict__[LAYOUT_MARK] == LogLayout.INFERENCE_CALL_END
        assert _fields(record) == {
            GenAISpanAttr.OPERATION_NAME: "chat",
            "model_handle": "gpt-test",
            "backend_name": "stand_in_backend",
            "sdk": "stand_in_sdk",
            GenAISpanAttr.REQUEST_MODEL: "gpt-test",
            GenAISpanAttr.RESPONSE_MODEL: "gpt-test-2026",
            GenAISpanAttr.USAGE_INPUT_TOKENS: reported_usage.nb_tokens_by_category[TokenCategory.INPUT],
            GenAISpanAttr.USAGE_OUTPUT_TOKENS: reported_usage.nb_tokens_by_category[TokenCategory.OUTPUT],
            "cost_usd": compute_tokens_usage_cost(reported_usage),
            "duration_ms": DURATION_MS,
            "outcome": "success",
        }
        assert math.isclose(_fields(record)["cost_usd"], 0.0018)

    @pytest.mark.asyncio
    async def test_the_model_keys_mean_what_the_llm_span_makes_them_mean(
        self, caplog: pytest.LogCaptureFixture, span_exporter: InMemorySpanExporter
    ) -> None:
        otel_context = OtelContext(trace_id=RUN_TRACE_ID, trace_name="some_pipe", trace_name_redacted="some_pipe", span_id=PIPE_SPAN_ID)

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await _StandInLLMWorker(usage=LLM_USAGE).gen_text(llm_job=_llm_job(otel_context=otel_context))

        (record,) = _summaries(caplog)
        (span,) = span_exporter.get_finished_spans()
        assert span.attributes is not None
        for key in (GenAISpanAttr.REQUEST_MODEL, GenAISpanAttr.RESPONSE_MODEL, GenAISpanAttr.USAGE_INPUT_TOKENS, GenAISpanAttr.USAGE_OUTPUT_TOKENS):
            assert getattr(record, key) == span.attributes[key], key

    @pytest.mark.asyncio
    async def test_a_call_failing_before_the_provider_answers_says_so_and_carries_no_usage(self, caplog: pytest.LogCaptureFixture) -> None:
        worker = _StandInLLMWorker(error=LLMCompletionError(message="provider refused"))

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER), pytest.raises(LLMCompletionError, match="provider refused"):
            await worker.gen_text(llm_job=_llm_job())

        (record,) = _summaries(caplog)
        fields = _fields(record)
        assert (fields["outcome"], fields["error.type"], fields["duration_ms"]) == ("error", "LLMCompletionError", DURATION_MS)
        assert GenAISpanAttr.USAGE_INPUT_TOKENS not in fields
        assert GenAISpanAttr.USAGE_OUTPUT_TOKENS not in fields
        assert "cost_usd" not in fields

    @pytest.mark.asyncio
    async def test_a_failure_the_provider_billed_carries_its_usage_and_cost(self, caplog: pytest.LogCaptureFixture) -> None:
        """A search whose answer a guard refuses was answered and billed, and the reporting path reports it: so does the event."""
        worker = _StandInSearchWorker(error=SearchJobFailureError(message="the answer had no sources"))

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER), pytest.raises(SearchJobFailureError):
            await worker.search_sourced_answer(search_job=_search_job())

        (record,) = _summaries(caplog)
        fields = _fields(record)
        assert math.isclose(fields.pop("cost_usd"), OTHER_COST_USD)
        assert fields == {
            GenAISpanAttr.OPERATION_NAME: "search",
            "model_handle": "search-test",
            "backend_name": "stand_in_backend",
            "sdk": "stand_in_sdk",
            GenAISpanAttr.REQUEST_MODEL: "search-test",
            GenAISpanAttr.RESPONSE_MODEL: "search-test-2026",
            **OTHER_TOKEN_FIELDS,
            "duration_ms": DURATION_MS,
            "outcome": "error",
            "error.type": "SearchJobFailureError",
        }

    @pytest.mark.parametrize(("run_call", "operation", "model_names"), FAMILY_CASES, ids=FAMILY_IDS)
    @pytest.mark.asyncio
    async def test_every_family_ends_its_call_with_the_event_under_its_operation(
        self,
        caplog: pytest.LogCaptureFixture,
        run_call: Callable[[], Awaitable[None]],
        operation: InferenceOperation,
        model_names: tuple[str, str],
    ) -> None:
        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await run_call()

        (record,) = _summaries(caplog)
        handle, model_id = model_names
        fields = _fields(record)
        assert math.isclose(fields.pop("cost_usd"), OTHER_COST_USD)
        assert fields == {
            GenAISpanAttr.OPERATION_NAME: operation,
            "model_handle": handle,
            "backend_name": "stand_in_backend",
            "sdk": "stand_in_sdk",
            GenAISpanAttr.REQUEST_MODEL: handle,
            GenAISpanAttr.RESPONSE_MODEL: model_id,
            **OTHER_TOKEN_FIELDS,
            "duration_ms": DURATION_MS,
            "outcome": "success",
        }

    def test_a_document_print_ends_with_the_event_and_no_usage_at_all(self, caplog: pytest.LogCaptureFixture) -> None:
        """A document engine reports no usage, so its event carries no tokens and no cost, rather than zeros."""
        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            job = RenderJob(
                format=DocGenFormat.PDF,
                source=DocGenSource.LAYOUT,
                filename="summary.pdf",
                title="Summary",
                layout=LayoutDocument(title="Summary", blocks=[MarkdownBlock(markdown="Hello")]),
            )
            get_test_renderer().print_document(job=job, resources=StubRenderResources())

        (record,) = _summaries(caplog)
        assert _fields(record) == {
            GenAISpanAttr.OPERATION_NAME: "doc_gen",
            "model_handle": "reportlab-pdf",
            "backend_name": "internal",
            "sdk": "reportlab",
            GenAISpanAttr.REQUEST_MODEL: "reportlab-pdf",
            GenAISpanAttr.RESPONSE_MODEL: "print-pdf",
            "duration_ms": DURATION_MS,
            "outcome": "success",
        }

    @pytest.mark.asyncio
    async def test_an_extraction_priced_by_its_pages_carries_its_cost_and_no_page_counts_as_tokens(self, caplog: pytest.LogCaptureFixture) -> None:
        """The base records three pages as three million tokens in and out so the rate table prices a page; a page is not a token."""
        extract_job = _extract_job()

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await _StandInExtractWorker(usage=None).extract_pages(extract_job=extract_job)

        (record,) = _summaries(caplog)
        fields = _fields(record)
        reported_usage = extract_job.job_report.extract_tokens_usage
        assert reported_usage is not None
        assert reported_usage.nb_tokens_by_category == {TokenCategory.INPUT: 3_000_000, TokenCategory.OUTPUT: 3_000_000}
        assert fields["cost_usd"] == compute_tokens_usage_cost(reported_usage)
        assert math.isclose(fields["cost_usd"], 9.0)
        assert GenAISpanAttr.USAGE_INPUT_TOKENS not in fields
        assert GenAISpanAttr.USAGE_OUTPUT_TOKENS not in fields

    @pytest.mark.asyncio
    async def test_an_unrated_model_carries_its_tokens_and_no_cost(self, caplog: pytest.LogCaptureFixture) -> None:
        """A model with no rate table, one run on its own GPUs, has no price: the cost is left off rather than written as zero."""
        worker = _StandInLLMWorker(usage=LLM_USAGE)
        worker.inference_model = _model(model_type=ModelType.LLM, name="local-test", model_id="local-test-1", costs={})

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await worker.gen_text(llm_job=_llm_job())

        (record,) = _summaries(caplog)
        fields = _fields(record)
        assert (fields[GenAISpanAttr.USAGE_INPUT_TOKENS], fields[GenAISpanAttr.USAGE_OUTPUT_TOKENS]) == (1200, 300)
        assert "cost_usd" not in fields

    @pytest.mark.asyncio
    async def test_the_json_sink_writes_the_tokens_the_cost_and_the_duration_as_numbers(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await _StandInLLMWorker(usage=LLM_USAGE).gen_text(llm_job=_llm_job())
        (record,) = _summaries(caplog)
        buffer = io.StringIO()

        JsonLogSink(stream=buffer).handler.handle(record)

        line: dict[str, Any] = json.loads(buffer.getvalue())
        assert (line[MESSAGE_KEY], line[LOGGER_KEY]) == (INFERENCE_CALL_ENDS_MESSAGE, SUMMARY_LOGGER)
        assert line[GenAISpanAttr.USAGE_INPUT_TOKENS] == 1200
        assert line[GenAISpanAttr.USAGE_OUTPUT_TOKENS] == 300
        assert isinstance(line[GenAISpanAttr.USAGE_INPUT_TOKENS], int)
        assert isinstance(line[GenAISpanAttr.USAGE_OUTPUT_TOKENS], int)
        assert isinstance(line["cost_usd"], float)
        assert math.isclose(line["cost_usd"], 0.0018)
        assert isinstance(line["duration_ms"], float)
        assert line["duration_ms"] == DURATION_MS
        assert (line[GenAISpanAttr.OPERATION_NAME], line["outcome"]) == ("chat", "success")
        assert LogLayout.INFERENCE_CALL_END not in line.values()

    @pytest.mark.asyncio
    async def test_the_console_draws_the_call_on_one_compact_line(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await _StandInLLMWorker(usage=LLM_USAGE).gen_text(llm_job=_llm_job())
            with pytest.raises(LLMCompletionError):
                await _StandInLLMWorker(error=LLMCompletionError(message="provider refused")).gen_text(llm_job=_llm_job())

        succeeded, failed = _summaries(caplog)
        assert rendered_text(record=succeeded).plain == "🧠: gpt-test chat · 1,200 → 300 tokens · $0.0018 · done in 1.25 s"
        assert rendered_text(record=failed).plain == "🧠: gpt-test chat · failed after 1.25 s error.type=LLMCompletionError"
