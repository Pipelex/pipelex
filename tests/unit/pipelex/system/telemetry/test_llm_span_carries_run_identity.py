"""The LLM generation span carries the run's identity.

`$ai_generation` is the artifact the whole campaign exists for: on the hosted
plane every one of them used to be attributed to the deployment. The exporter
resolves per span, which only helps if the span site actually writes the run's
identity onto the span — so this drives the real `_start_otel_span_llm` on a real
`LLMJob` and reads the attributes back off the span OTel produced.
"""

from typing import Any

from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_abstract import LLMWorkerAbstract
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.system.job_metadata import JobMetadata, OtelContext, RunMetadata, UnitJobId
from pipelex.system.telemetry.otel_constants import LangfuseSpanAttr, OTelConstants, PipelexSpanAttr
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class _StubLLMWorker(LLMWorkerAbstract):
    """A worker that is never asked to generate — only to build a span."""

    @override
    async def _gen_text(self, llm_job: LLMJob) -> str:
        raise NotImplementedError

    @override
    async def _gen_object(self, llm_job: LLMJob, *, schema: type[BaseModelTypeVar]) -> BaseModelTypeVar:
        raise NotImplementedError


def _make_worker() -> _StubLLMWorker:
    inference_model = InferenceModelSpec(
        backend_name="openai",
        name="gpt-test",
        sdk="openai",
        model_type=ModelType.LLM,
        model_id="gpt-test-id",
        inputs=["text"],
        outputs=["text"],
        costs={CostCategory.INPUT: 1, CostCategory.OUTPUT: 2},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return _StubLLMWorker(inference_model=inference_model)


def _make_llm_job(*, analytics_groups: dict[str, str] | None = None) -> LLMJob:
    job_metadata = JobMetadata(
        run_metadata=RunMetadata(
            user_id="user-42",
            pipeline_run_id="run-1",
            storage_scope="tenant/run-1",
            analytics_groups=analytics_groups or {},
        ),
        pipe_code="some_pipe",
        unit_job_id=UnitJobId.LLM_GEN_TEXT,
        otel_context=OtelContext(
            trace_id=1234,
            trace_name="some_pipe_abc12345",
            trace_name_redacted="abc12345",
            span_id=OTelConstants.OTEL_VIRTUAL_ROOT_PARENT_SPAN_ID,
        ),
    )
    return LLMJob(
        job_metadata=job_metadata,
        llm_prompt=LLMPrompt(user_text="hello"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
    )


def _start_span(*, mocker: MockerFixture, llm_job: LLMJob) -> SdkSpan:
    mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=TracerProvider().get_tracer("test"))
    span = _make_worker()._start_otel_span_llm(llm_job=llm_job, output_type=InferenceOutputType.TEXT)  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    assert isinstance(span, SdkSpan)
    return span


def _attributes(span: SdkSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


class TestLLMSpanIdentity:
    def test_the_span_names_the_runs_user(self, mocker: MockerFixture) -> None:
        span = _start_span(mocker=mocker, llm_job=_make_llm_job())

        assert _attributes(span)[PipelexSpanAttr.RUN_USER_ID] == "user-42"

    def test_the_span_carries_the_runs_groups_serialized(self, mocker: MockerFixture) -> None:
        span = _start_span(mocker=mocker, llm_job=_make_llm_job(analytics_groups={"organization": "org_acme"}))

        assert _attributes(span)[PipelexSpanAttr.RUN_ANALYTICS_GROUPS] == '{"organization": "org_acme"}'

    def test_a_run_with_no_groups_writes_no_groups_attribute(self, mocker: MockerFixture) -> None:
        span = _start_span(mocker=mocker, llm_job=_make_llm_job())

        assert PipelexSpanAttr.RUN_ANALYTICS_GROUPS not in _attributes(span)

    def test_langfuse_gets_the_user_id_only_when_it_is_enabled(self, mocker: MockerFixture) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "get_langfuse_enabled", return_value=True)
        span = _start_span(mocker=mocker, llm_job=_make_llm_job())

        assert _attributes(span)[LangfuseSpanAttr.USER_ID] == "user-42"

    def test_langfuse_user_id_is_absent_when_langfuse_is_off(self, mocker: MockerFixture) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "get_langfuse_enabled", return_value=False)
        span = _start_span(mocker=mocker, llm_job=_make_llm_job())

        assert LangfuseSpanAttr.USER_ID not in _attributes(span)
