from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, cast

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from typing_extensions import override

from pipelex.cogt.content_generation import doc_gen_generate
from pipelex.cogt.content_generation.assignment_models import RenderDocumentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.doc_gen_generate import render_document_and_store
from pipelex.cogt.doc_gen import doc_gen_engine
from pipelex.cogt.doc_gen.doc_gen_format import DocGenFormat, DocGenSource
from pipelex.cogt.doc_gen.doc_gen_setting import DocGenSetting
from pipelex.cogt.doc_gen.doc_gen_worker_abstract import DocGenWorkerAbstract
from pipelex.cogt.doc_gen.doc_gen_worker_factory import DocGenWorkerFactory
from pipelex.cogt.doc_gen.document_composition import DocumentComposition
from pipelex.cogt.doc_gen.exceptions import DocGenEngineMissingError
from pipelex.cogt.doc_gen.layout_tree import ImageBlock, LayoutBlock, LayoutDocument, MarkdownBlock
from pipelex.cogt.doc_gen.render_job import RenderedDocument
from pipelex.cogt.exceptions import (
    ExtractCapabilityError,
    ImgGenParameterError,
    LLMCapabilityError,
    LLMCompletionError,
    ModelNotFoundError,
    SearchJobFailureError,
)
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams, ExtractJobReport
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.prompt_image import PromptImageUri
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
from pipelex.cogt.usage.pricing_unit import PricingUnit
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.cogt.usage.usage_cost import compute_tokens_usage_cost
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.telemetry.current_span import PIPELEX_SPAN_ID_KEY
from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.console_layouts import LogLayout
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log_fields import LAYOUT_MARK, attached_field_names
from pipelex.tools.log.summary_event import SUMMARY_EVENT_FAILED_MESSAGE
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.exceptions import UriReadRefusedError
from tests.helpers.console_log_rendering import rendered_text
from tests.unit.pipelex.cogt.judgment.fake_judgment_worker import make_fake_judgment_job
from tests.unit.pipelex.providers.reportlab.reportlab_test_helpers import reportlab_pdf_model

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from pytest_mock import MockerFixture

    from pipelex.cogt.doc_gen.render_job import RenderJob, RenderResources
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
# The model a routing LLM worker names once `_before_job` has routed the call, and the one the provider says served it.
ROUTED_MODEL = "gpt-test-routed"
SERVED_MODEL = "gpt-test-2026-10-01"
# The document engine's model keys, as the kit's `internal.toml` declares `reportlab-pdf`.
REPORTLAB_MODEL_FIELDS: dict[str, Any] = {
    "model_handle": "reportlab-pdf",
    "backend_name": "internal",
    "sdk": "reportlab",
    GenAISpanAttr.REQUEST_MODEL: "reportlab-pdf",
    GenAISpanAttr.RESPONSE_MODEL: "print-pdf",
}
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
    def __init__(self, *, usage: NbTokensByCategoryDict | None = None, error: BaseException | None = None, reporting_delegate: Any = None) -> None:
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


class _RoutingLLMWorker(_StandInLLMWorker):
    """Names the model it routes the call to in `_before_job`, and learns from the provider which model served the call."""

    def __init__(self) -> None:
        super().__init__(usage=LLM_USAGE)
        self._routed_model = "gpt-test"
        self._served_model = "gpt-test-2026"

    @override
    async def _before_job(self, llm_job: LLMJob) -> None:
        await super()._before_job(llm_job=llm_job)
        self._routed_model = ROUTED_MODEL

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        self._served_model = SERVED_MODEL
        return await super()._gen_text(llm_job=llm_job)

    @override
    def _get_request_model_name(self) -> str:
        return self._routed_model

    @override
    def _get_response_model_name(self) -> str:
        return self._served_model


class _BlockingEngine(DocGenWorkerAbstract):
    """A document engine whose render waits until the test releases it, as a long print does."""

    def __init__(self) -> None:
        super().__init__(inference_model=reportlab_pdf_model())
        self.has_started = threading.Event()
        self.release = threading.Event()

    @override
    def render(self, *, job: RenderJob, resources: RenderResources) -> RenderedDocument:
        self.has_started.set()
        self.release.wait(timeout=10)
        return RenderedDocument(data=b"%PDF-1.4")


def _render_assignment(
    *, model_handle: str = "reportlab-pdf", read_scope: str | None = None, image_url: str | None = None
) -> RenderDocumentAssignment:
    blocks: list[LayoutBlock] = [MarkdownBlock(markdown="Hello")]
    if image_url is not None:
        blocks.append(ImageBlock(url=image_url))
    return RenderDocumentAssignment(
        job_metadata=JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", storage_scope="org_abc/run", read_scope=read_scope, pipeline_run_id="plr-summary"),
            pipe_code="print_summary",
        ),
        cogt_run_params=CogtRunParams(run_mode=PipeRunMode.LIVE),
        composition=DocumentComposition(
            format=DocGenFormat.PDF,
            source=DocGenSource.LAYOUT,
            filename="summary.pdf",
            title="Summary",
            layout=LayoutDocument(title="Summary", blocks=blocks),
        ),
        doc_gen_setting=DocGenSetting(model=model_handle),
    )


def _generated_content_factory(mocker: MockerFixture) -> Any:
    """The factory a print stores its file through, standing in for the run's storage."""
    factory = mocker.MagicMock()
    factory.storage_provider = mocker.MagicMock(spec=StorageProviderAbstract)
    factory.make_document_content = mocker.AsyncMock(return_value="the stored document")
    return factory


def _llm_job(*, otel_context: OtelContext | None = None, llm_prompt: LLMPrompt | None = None) -> LLMJob:
    return LLMJob(
        job_metadata=_job_metadata(otel_context=otel_context),
        llm_prompt=llm_prompt or LLMPrompt(user_text="hello"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def _extract_job(*, extract_input: ExtractInput | None = None) -> ExtractJob:
    return ExtractJob(
        extract_input=extract_input or ExtractInput(document_uri="https://example.com/report.pdf"),
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

# A picture handed to models that read only text or only PDFs, which the checks before the call refuse.
CAT_PICTURE = PromptImageUri(uri="https://example.com/cat.png")


async def _refuse_llm() -> None:
    await _StandInLLMWorker(usage=LLM_USAGE).gen_text(llm_job=_llm_job(llm_prompt=LLMPrompt(user_text="describe it", user_images=[CAT_PICTURE])))


async def _refuse_img_gen() -> None:
    img_gen_job = ImgGenJobFactory.make_img_gen_job_from_prompt_contents("a cat", negative_text=None, job_metadata=_job_metadata())
    img_gen_job.img_gen_prompt.input_images = [CAT_PICTURE]
    await _StandInImgGenWorker().gen_image(img_gen_job=img_gen_job)


async def _refuse_extract() -> None:
    extract_job = _extract_job(extract_input=ExtractInput(image_uri="https://example.com/scan.png"))
    await _StandInExtractWorker(usage=OTHER_USAGE).extract_pages(extract_job=extract_job)


REFUSAL_CASES: list[tuple[Callable[[], Awaitable[None]], type[Exception], InferenceOperation]] = [
    (_refuse_llm, LLMCapabilityError, InferenceOperation.CHAT),
    (_refuse_img_gen, ImgGenParameterError, InferenceOperation.IMG_GEN),
    (_refuse_extract, ExtractCapabilityError, InferenceOperation.EXTRACT),
]
REFUSAL_IDS = ["an LLM without vision given a picture", "an image model given an input image", "a PDF extractor given an image"]
# A print each check before the engine refuses: what the assignment asks, whether the engine's plugin is installed, the
# refusal, and the model keys the event names it by, the handle alone where the print ended before the model resolved.
FOREIGN_IMAGE = "pipelex-storage://org_other/assets/secret.png"
DOC_GEN_REFUSAL_CASES: list[tuple[dict[str, Any], bool, type[Exception], dict[str, Any]]] = [
    (
        {"read_scope": "org_abc", "image_url": FOREIGN_IMAGE},
        True,
        UriReadRefusedError,
        {"model_handle": "reportlab-pdf", GenAISpanAttr.REQUEST_MODEL: "reportlab-pdf"},
    ),
    ({"model_handle": "no-such-engine"}, True, ModelNotFoundError, {"model_handle": "no-such-engine", GenAISpanAttr.REQUEST_MODEL: "no-such-engine"}),
    ({}, False, DocGenEngineMissingError, REPORTLAB_MODEL_FIELDS),
]
DOC_GEN_REFUSAL_IDS = ["an image outside the read scope", "an engine no model here serves", "an engine no plugin registers"]
# A count the provider half recorded as nothing at all, which the cost engine cannot subtract from.
BROKEN_USAGE = cast("NbTokensByCategoryDict", {TokenCategory.INPUT: None, TokenCategory.OUTPUT: 300})


def _summaries(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == SUMMARY_LOGGER and record.getMessage() == INFERENCE_CALL_ENDS_MESSAGE]


def _fields(record: logging.LogRecord) -> dict[str, Any]:
    """The fields the call attached to the record, read the way a sink reads them."""
    return {name: getattr(record, name) for name in attached_field_names(record=record)}


@pytest.fixture
def fixed_clock(mocker: MockerFixture) -> None:
    """Every call starts at the same reading and ends 1.25 s later, so its duration is known."""
    mocker.patch("pipelex.tools.log.summary_event.start_clock", return_value=STARTED_AT)
    mocker.patch("pipelex.tools.log.summary_fields.perf_counter", return_value=ENDED_AT)


@pytest.fixture
def span_exporter(mocker: MockerFixture) -> InMemorySpanExporter:
    """The runtime's tracer, replaced by one exporting to memory, so the test reads back the span the worker started."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer(__name__))
    return exporter


@pytest.fixture
def json_lines() -> Iterator[io.StringIO]:
    """The `json` sink's lines for every event the summary logger writes, written as it logs them, with the span active then."""
    buffer = io.StringIO()
    handler = JsonLogSink(stream=buffer).handler
    summary_logger = logging.getLogger(SUMMARY_LOGGER)
    summary_logger.addHandler(handler)
    try:
        yield buffer
    finally:
        summary_logger.removeHandler(handler)


def _read_json_lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line]


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

    @pytest.mark.asyncio
    async def test_a_document_print_ends_with_the_event_and_no_usage_at_all(self, caplog: pytest.LogCaptureFixture, mocker: MockerFixture) -> None:
        """A document engine reports no usage, so its event carries no tokens and no cost, rather than zeros."""
        generated_content_factory = _generated_content_factory(mocker)

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            stored = await render_document_and_store(_render_assignment(), generated_content_factory=generated_content_factory)

        assert stored == "the stored document"
        assert generated_content_factory.make_document_content.await_args.kwargs["data"].startswith(b"%PDF")
        (record,) = _summaries(caplog)
        assert _fields(record) == {
            GenAISpanAttr.OPERATION_NAME: "doc_gen",
            **REPORTLAB_MODEL_FIELDS,
            "duration_ms": DURATION_MS,
            "outcome": "success",
        }

    @pytest.mark.parametrize(
        ("assignment_kwargs", "is_engine_installed", "refusal_type", "model_fields"), DOC_GEN_REFUSAL_CASES, ids=DOC_GEN_REFUSAL_IDS
    )
    @pytest.mark.asyncio
    async def test_a_document_print_the_checks_refuse_ends_with_the_event_too(
        self,
        caplog: pytest.LogCaptureFixture,
        mocker: MockerFixture,
        assignment_kwargs: dict[str, Any],
        is_engine_installed: bool,
        refusal_type: type[Exception],
        model_fields: dict[str, Any],
    ) -> None:
        """The read scope, the engine's model and its installation are checked inside the event, as every other family's checks are."""
        if not is_engine_installed:
            mocker.patch.object(doc_gen_engine, "get_inference_backend_registry").return_value.has.return_value = False
        generated_content_factory = _generated_content_factory(mocker)

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER), pytest.raises(refusal_type):
            await render_document_and_store(_render_assignment(**assignment_kwargs), generated_content_factory=generated_content_factory)

        generated_content_factory.make_document_content.assert_not_awaited()
        (record,) = _summaries(caplog)
        assert _fields(record) == {
            GenAISpanAttr.OPERATION_NAME: "doc_gen",
            **model_fields,
            "duration_ms": DURATION_MS,
            "outcome": "error",
            "error.type": refusal_type.__name__,
        }

    @pytest.mark.asyncio
    async def test_a_document_print_cancelled_from_outside_ends_cancelled_once_whatever_its_thread_does_after(
        self, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
    ) -> None:
        """The event follows the coroutine awaiting the print: the engine's thread, which nothing stops, ends its render unheard."""
        engine = _BlockingEngine()
        mocker.patch.object(DocGenWorkerFactory, "make_doc_gen_worker", return_value=engine)
        print_pool = ThreadPoolExecutor(max_workers=1)
        mocker.patch.object(doc_gen_generate, "_PRINT_EXECUTOR", print_pool)

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            print_task = asyncio.create_task(
                render_document_and_store(_render_assignment(), generated_content_factory=_generated_content_factory(mocker))
            )
            assert await asyncio.to_thread(engine.has_started.wait, 10)
            print_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await print_task
            engine.release.set()
            # The engine's thread has returned from its render once the pool it ran on has shut down.
            await asyncio.to_thread(print_pool.shutdown, wait=True)

        (record,) = _summaries(caplog)
        fields = _fields(record)
        assert (fields["outcome"], fields["duration_ms"]) == ("cancelled", DURATION_MS)
        assert "error.type" not in fields

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
        assert reported_usage.pricing_unit is PricingUnit.PAGE
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

    @pytest.mark.parametrize(("refuse_call", "refusal_type", "operation"), REFUSAL_CASES, ids=REFUSAL_IDS)
    @pytest.mark.asyncio
    async def test_a_call_the_checks_refuse_ends_with_the_event_too(
        self,
        caplog: pytest.LogCaptureFixture,
        refuse_call: Callable[[], Awaitable[None]],
        refusal_type: type[Exception],
        operation: InferenceOperation,
    ) -> None:
        """A refusal before the provider is called is a call that failed: it ends with the event, its error type and no usage."""
        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER), pytest.raises(refusal_type):
            await refuse_call()

        (record,) = _summaries(caplog)
        fields = _fields(record)
        assert fields[GenAISpanAttr.OPERATION_NAME] == operation
        assert (fields["outcome"], fields["error.type"], fields["duration_ms"]) == ("error", refusal_type.__name__, DURATION_MS)
        assert {GenAISpanAttr.USAGE_INPUT_TOKENS, GenAISpanAttr.USAGE_OUTPUT_TOKENS, "cost_usd"}.isdisjoint(fields)

    @pytest.mark.asyncio
    async def test_the_llm_event_carries_the_calls_span_and_a_refused_call_names_none(
        self, caplog: pytest.LogCaptureFixture, span_exporter: InMemorySpanExporter, json_lines: io.StringIO
    ) -> None:
        otel_context = OtelContext(trace_id=RUN_TRACE_ID, trace_name="some_pipe", trace_name_redacted="some_pipe", span_id=PIPE_SPAN_ID)

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await _StandInLLMWorker(usage=LLM_USAGE).gen_text(llm_job=_llm_job(otel_context=otel_context))
            with pytest.raises(LLMCapabilityError):
                await _StandInLLMWorker(usage=LLM_USAGE).gen_text(
                    llm_job=_llm_job(otel_context=otel_context, llm_prompt=LLMPrompt(user_text="describe it", user_images=[CAT_PICTURE]))
                )

        (span,) = span_exporter.get_finished_spans()
        span_context = span.get_span_context()
        assert span_context is not None
        succeeded, refused = _read_json_lines(json_lines)
        assert (succeeded["outcome"], succeeded[PIPELEX_SPAN_ID_KEY]) == ("success", f"{span_context.span_id:016x}")
        assert refused["outcome"] == "error"
        assert PIPELEX_SPAN_ID_KEY not in refused

    @pytest.mark.asyncio
    async def test_a_cancelled_call_ends_with_a_cancelled_outcome_and_no_error_type(self, caplog: pytest.LogCaptureFixture) -> None:
        """A call cancelled from outside, as a batch cancels its siblings when one fails, is not a failure of the call."""
        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER), pytest.raises(asyncio.CancelledError):
            await _StandInLLMWorker(error=asyncio.CancelledError()).gen_text(llm_job=_llm_job())

        (record,) = _summaries(caplog)
        fields = _fields(record)
        assert (fields["outcome"], fields["duration_ms"]) == ("cancelled", DURATION_MS)
        assert "error.type" not in fields
        assert rendered_text(record=record).plain == "🧠: gpt-test chat · cancelled after 1.25 s"

    @pytest.mark.parametrize("provider_error", [None, LLMCompletionError(message="provider refused")], ids=["the call succeeds", "the call fails"])
    @pytest.mark.asyncio
    async def test_an_event_that_cannot_be_priced_never_changes_the_calls_outcome(
        self, caplog: pytest.LogCaptureFixture, provider_error: LLMCompletionError | None
    ) -> None:
        """A usage the cost engine cannot price is logged once as a warning; the call's result or its own error goes on."""
        worker = _StandInLLMWorker(usage=BROKEN_USAGE, error=provider_error)

        with caplog.at_level(logging.INFO):
            if provider_error is None:
                assert await worker.gen_text(llm_job=_llm_job()) == "answer"
            else:
                with pytest.raises(LLMCompletionError, match="provider refused") as raised:
                    await worker.gen_text(llm_job=_llm_job())
                assert raised.value is provider_error

        assert not _summaries(caplog)
        (failure,) = [record for record in caplog.records if record.getMessage() == SUMMARY_EVENT_FAILED_MESSAGE]
        failure_fields = _fields(failure)
        assert failure.levelno == logging.WARNING
        assert (failure_fields["summary_event"], failure_fields["error.type"]) == (INFERENCE_CALL_ENDS_MESSAGE, "TypeError")

    @pytest.mark.asyncio
    async def test_the_model_names_are_read_when_the_call_ends(self, caplog: pytest.LogCaptureFixture, span_exporter: InMemorySpanExporter) -> None:
        """A worker routing the call in `_before_job` is named as its span names it, and the model the provider served is the one named."""
        otel_context = OtelContext(trace_id=RUN_TRACE_ID, trace_name="some_pipe", trace_name_redacted="some_pipe", span_id=PIPE_SPAN_ID)

        with caplog.at_level(logging.INFO, logger=SUMMARY_LOGGER):
            await _RoutingLLMWorker().gen_text(llm_job=_llm_job(otel_context=otel_context))

        (record,) = _summaries(caplog)
        (span,) = span_exporter.get_finished_spans()
        assert span.attributes is not None
        fields = _fields(record)
        assert fields[GenAISpanAttr.REQUEST_MODEL] == span.attributes[GenAISpanAttr.REQUEST_MODEL] == ROUTED_MODEL
        assert fields[GenAISpanAttr.RESPONSE_MODEL] == SERVED_MODEL
