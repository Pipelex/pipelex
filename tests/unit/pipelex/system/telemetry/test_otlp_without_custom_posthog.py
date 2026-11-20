from __future__ import annotations

from typing import TYPE_CHECKING, Any

import posthog
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.singleton import MetaSingleton
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.otel_constants import OTelConstants, PipelexSpanAttr
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_config import OtlpExporterConfig, PostHogConfig, PostHogMode, TelemetryConfig
from pipelex.system.telemetry.telemetry_factory import TelemetryFactory
from pipelex.system.telemetry.telemetry_manager import TelemetryManager
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate

PIPELINE_RUN_ID = "plr-otlp-without-posthog"
PIPE_CODE = "traced_without_posthog"
_OTLP = OtlpExporterConfig(name="collector", endpoint="https://collector.example.test/v1/traces", headers={"authorization": "Bearer test-token"})


class TracedPipe(PipeAbstract):
    """A pipe whose live run does nothing but return, so its only span is the pipe's own."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"

    @override
    def validate_inputs_with_library(self) -> None: ...

    @override
    def validate_inputs_static(self) -> None: ...

    @override
    def validate_output_with_library(self) -> None: ...

    @override
    def validate_output_static(self) -> None: ...

    @override
    async def _validate_before_run(self, **kwargs: Any) -> None: ...

    @override
    async def _validate_after_run(self, **kwargs: Any) -> None: ...

    @override
    def required_variables(self) -> set[str]:
        return set()

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> Any:
        return self.inputs

    @override
    async def _live_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        return PipeOutput(working_memory=working_memory, pipeline_run_id=job_metadata.run_metadata.pipeline_run_id)

    @override
    async def _dry_run_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: LibraryCrate | None = None,
    ) -> PipeOutput:
        raise NotImplementedError


@pytest.mark.asyncio
class TestOtlpWithoutCustomPostHog:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY, raising=False)
        monkeypatch.delenv(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY, raising=False)

    async def test_a_runs_spans_reach_the_otlp_exporter_with_posthog_off(self, mocker: MockerFixture) -> None:
        """The real manager boots with join_host_trace on, and a live run's pipe span reaches the exporter once teardown flushes it."""
        # The singleton registry is restored when the test ends, so the manager made here and its teardown leave the session's alone.
        mocker.patch.dict(MetaSingleton.instances)
        MetaSingleton.instances.pop(TelemetryManager, None)
        otlp_exporter = InMemorySpanExporter()
        otlp_exporter_class = mocker.patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", return_value=otlp_exporter)
        posthog_class = mocker.patch("pipelex.system.telemetry.telemetry_manager.Posthog")
        # A host application's own module-level PostHog client, which a manager made for span destinations alone must leave alone.
        host_posthog_client = mocker.sentinel.host_posthog_client
        mocker.patch("posthog.default_client", host_posthog_client)
        mocker.patch("posthog.privacy_mode", False)
        telemetry_config = TelemetryConfig(
            join_host_trace=True,
            custom_posthog=PostHogConfig(mode=PostHogMode.OFF),
            otlp=[_OTLP],
            telemetry_allowed_modes={"fastapi": True},
        )

        telemetry_manager = TelemetryFactory.make_telemetry_manager(
            secrets_provider=EnvSecretsProvider(),
            integration_mode=IntegrationMode.FASTAPI,
            telemetry_config=telemetry_config,
        )

        assert isinstance(telemetry_manager, TelemetryManager)
        assert telemetry_manager.join_host_trace is True
        assert telemetry_manager.custom_posthog_client is None
        posthog_class.assert_not_called()
        assert posthog.default_client is host_posthog_client
        assert posthog.privacy_mode is False
        otlp_exporter_class.assert_called_once_with(endpoint=_OTLP.endpoint, headers=_OTLP.headers)
        tracer = telemetry_manager.get_otel_tracer()
        assert tracer is not None
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=tracer)

        pipe = TracedPipe(
            code=PIPE_CODE,
            domain_code="test_otlp_without_posthog",
            description="A pipe traced to OTLP alone",
            output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        )
        otel_context = OtelFactory.make_run_otel_context(pipeline_run_id=PIPELINE_RUN_ID, pipe_code=PIPE_CODE, host_span=None)
        job_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id=PIPELINE_RUN_ID),
            otel_context=otel_context,
        )
        await pipe.live_run_pipe(
            job_metadata=job_metadata,
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10),
        )
        telemetry_manager.teardown()

        (pipe_span,) = otlp_exporter.get_finished_spans()
        assert pipe_span.name == f"TracedPipe: {PIPE_CODE}"
        span_context = pipe_span.get_span_context()
        assert span_context is not None
        assert span_context.trace_id == OtelFactory.make_trace_id(pipeline_run_id=PIPELINE_RUN_ID)
        assert pipe_span.attributes is not None
        assert pipe_span.attributes.get(PipelexSpanAttr.RUN_ROOT) is True

    async def test_an_exception_escapes_the_telemetry_context_unchanged_with_posthog_off(self, mocker: MockerFixture) -> None:
        """With no PostHog client, the context captures nothing, so PostHog's keyless module-level fallback never replaces the error."""
        mocker.patch.dict(MetaSingleton.instances)
        MetaSingleton.instances.pop(TelemetryManager, None)
        mocker.patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", return_value=InMemorySpanExporter())
        mocker.patch("posthog.default_client", None)
        mocker.patch("posthog.api_key", None)
        telemetry_config = TelemetryConfig(
            custom_posthog=PostHogConfig(mode=PostHogMode.OFF),
            otlp=[_OTLP],
            telemetry_allowed_modes={"fastapi": True},
        )
        telemetry_manager = TelemetryFactory.make_telemetry_manager(
            secrets_provider=EnvSecretsProvider(),
            integration_mode=IntegrationMode.FASTAPI,
            telemetry_config=telemetry_config,
        )

        try:
            assert isinstance(telemetry_manager, TelemetryManager)
            assert telemetry_manager.custom_posthog_client is None
            block_error = LookupError("the error the block raised")
            with pytest.raises(LookupError) as exc_info, telemetry_manager.telemetry_context():
                raise block_error
            assert exc_info.value is block_error
            assert posthog.default_client is None
        finally:
            telemetry_manager.teardown()

    async def test_posthog_on_without_span_tracing_sends_spans_to_otlp_but_none_to_posthog(self, mocker: MockerFixture) -> None:
        mocker.patch.dict(MetaSingleton.instances)
        MetaSingleton.instances.pop(TelemetryManager, None)
        mocker.patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", return_value=InMemorySpanExporter())
        mocker.patch("pipelex.system.telemetry.telemetry_manager.Posthog")
        mocker.patch("posthog.default_client", None)
        mocker.patch("posthog.privacy_mode", False)
        make_ai_tracer = mocker.spy(OtelFactory, "make_ai_tracer")
        telemetry_config = TelemetryConfig(
            custom_posthog=PostHogConfig(mode=PostHogMode.ANONYMOUS, api_key="phc_test"),
            otlp=[_OTLP],
            telemetry_allowed_modes={"fastapi": True},
        )

        telemetry_manager = TelemetryFactory.make_telemetry_manager(
            secrets_provider=EnvSecretsProvider(),
            integration_mode=IntegrationMode.FASTAPI,
            telemetry_config=telemetry_config,
        )

        try:
            assert isinstance(telemetry_manager, TelemetryManager)
            assert telemetry_manager.custom_posthog_client is not None
            assert telemetry_manager.get_otel_tracer() is not None
            # The client sends the stream's events; with its span tracing off, it is not handed to the tracer.
            assert make_ai_tracer.call_args.kwargs["custom_posthog_client"] is None
        finally:
            telemetry_manager.teardown()
