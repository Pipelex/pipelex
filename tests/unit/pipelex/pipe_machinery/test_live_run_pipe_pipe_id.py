from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import Field
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
from pipelex.system.telemetry.otel_constants import PipelexSpanAttr
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.pipe_identity import make_pipe_id, method_identity_of
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import ReadableSpan
    from pytest_mock import MockerFixture

    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate

_KEY = "k" * 32
_DOMAIN = "test_pipe_id"


def _no_pipe_ids() -> list[str | None]:
    return []


class PipeIdRecordingPipe(PipeAbstract):
    """A pipe whose live run records the `pipe_id` its job metadata hands to what it runs, and runs a nested pipe."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"
    nested: PipeIdRecordingPipe | None = None
    seen_pipe_ids: list[str | None] = Field(default_factory=_no_pipe_ids)

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
        self.seen_pipe_ids.append(job_metadata.pipe_id)
        if self.nested is not None:
            await self.nested.live_run_pipe(job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params)
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


def _make_pipe(*, code: str, nested: PipeIdRecordingPipe | None = None) -> PipeIdRecordingPipe:
    return PipeIdRecordingPipe(
        code=code,
        domain_code=_DOMAIN,
        description=code,
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        nested=nested,
    )


def _run_metadata() -> RunMetadata:
    return RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-pipe-id", method_id="mt_abc")


async def _run(pipe: PipeIdRecordingPipe) -> None:
    job_metadata = JobMetadata(
        run_metadata=_run_metadata(),
        otel_context=OtelFactory.make_run_otel_context(pipeline_run_id="plr-pipe-id", pipe_code=pipe.code, host_span=None),
    )
    await pipe.live_run_pipe(
        job_metadata=job_metadata,
        working_memory=WorkingMemoryFactory.make_empty(),
        pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10),
    )


def _expected_pipe_id(*, code: str) -> str:
    return make_pipe_id(key=_KEY, method_identity=method_identity_of(run_metadata=_run_metadata(), domain_code=_DOMAIN), pipe_ref=f"{_DOMAIN}.{code}")


def _span_attributes(spans: tuple[ReadableSpan, ...], *, code: str) -> dict[str, Any]:
    (span,) = [span for span in spans if span.name == f"PipeIdRecordingPipe: {code}"]
    return dict(span.attributes or {})


@pytest.mark.asyncio
class TestLiveRunPipePipeId:
    @pytest.fixture
    def pipelex_spans(self, mocker: MockerFixture) -> InMemorySpanExporter:
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        mocker.patch.object(TelemetryManagerAbstract, "get_instance_tracer", return_value=provider.get_tracer("pipelex"))
        return exporter

    async def test_each_pipe_span_carries_its_own_pipe_id_and_hands_it_to_what_the_pipe_runs(
        self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter
    ) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "get_pipe_id_key", return_value=_KEY)
        pipe = _make_pipe(code="outer", nested=_make_pipe(code="inner"))

        await _run(pipe)

        spans = pipelex_spans.get_finished_spans()
        outer_attributes = _span_attributes(spans, code="outer")
        inner_attributes = _span_attributes(spans, code="inner")
        assert outer_attributes[PipelexSpanAttr.PIPE_ID] == _expected_pipe_id(code="outer")
        assert inner_attributes[PipelexSpanAttr.PIPE_ID] == _expected_pipe_id(code="inner")
        assert outer_attributes[PipelexSpanAttr.RUN_METHOD_ID] == "mt_abc"
        # What each pipe runs, an inference call included, reads its pipe's id off the job metadata.
        assert pipe.seen_pipe_ids == [_expected_pipe_id(code="outer")]
        assert pipe.nested is not None
        assert pipe.nested.seen_pipe_ids == [_expected_pipe_id(code="inner")]

    async def test_without_a_key_no_span_carries_a_pipe_id(self, mocker: MockerFixture, pipelex_spans: InMemorySpanExporter) -> None:
        mocker.patch.object(TelemetryManagerAbstract, "get_pipe_id_key", return_value=None)
        pipe = _make_pipe(code="outer", nested=_make_pipe(code="inner"))

        await _run(pipe)

        spans = pipelex_spans.get_finished_spans()
        assert PipelexSpanAttr.PIPE_ID not in _span_attributes(spans, code="outer")
        assert PipelexSpanAttr.PIPE_ID not in _span_attributes(spans, code="inner")
        assert pipe.seen_pipe_ids == [None]
