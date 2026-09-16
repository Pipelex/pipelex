"""``live_run_pipe`` binds the pipe run's own id onto the log context for the pipe's execution.

The job metadata a submission builds carries no ``pipe_run_id``; the pipe mints one as it starts and
hands it down on a metadata copy. The binding here is what makes a record emitted inside the pipe
name the pipe run it belongs to, a nested pipe rebinding its own and the outer one coming back when
it returns. It is the binding every orchestration shares, so it lives on the pipe and not on the runner.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
from pydantic import Field
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.log.log_context import LogContext, get_log_context
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of

if TYPE_CHECKING:
    from pipelex.core.memory.working_memory import WorkingMemory
    from pipelex.libraries.library_crate import LibraryCrate


class Seen(NamedTuple):
    """What a recording pipe saw at one point of its run: its code, the metadata's pipe_run_id and the bound context."""

    code: str
    pipe_run_id: str | None
    context: LogContext | None


class RecordingPipe(PipeAbstract):
    """A pipe whose live run records the context it sees and, optionally, runs a nested pipe."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"
    nested: RecordingPipe | None = None
    seen: list[Seen] = Field(default_factory=empty_list_factory_of(Seen))

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
        self.seen.append(Seen(code=self.code, pipe_run_id=job_metadata.pipe_run_id, context=get_log_context()))
        log.info(f"inside {self.code}")
        if self.nested is not None:
            await self.nested.live_run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )
            self.seen.append(Seen(code=f"{self.code} after nested", pipe_run_id=job_metadata.pipe_run_id, context=get_log_context()))
            log.info(f"back in {self.code}")
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


def _make_pipe(*, code: str, nested: RecordingPipe | None = None) -> RecordingPipe:
    return RecordingPipe(
        code=code,
        domain_code="test_log_context",
        description=code,
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        nested=nested,
        seen=[],
    )


def _seam_shaped_metadata() -> JobMetadata:
    """What a submission builds: the run's identifiers, and no pipe_run_id yet."""
    return JobMetadata(run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", pipeline_run_id="plr-live", request_id="req-live"))


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == __name__]


def _field(record: logging.LogRecord, *, name: str) -> Any:
    """A field carried on the record: an attribute the stdlib does not declare, read the way a sink reads it."""
    return getattr(record, name)


@pytest.mark.asyncio
class TestLiveRunPipeLogContext:
    async def test_the_minted_pipe_run_id_is_bound_for_the_pipe_and_released_after(self, caplog: pytest.LogCaptureFixture) -> None:
        pipe = _make_pipe(code="outer")
        pipe_run_params = PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10)

        with caplog.at_level(logging.INFO), log.context(request_id="req-live", pipeline_run_id="plr-live"):
            await pipe.live_run_pipe(
                job_metadata=_seam_shaped_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=pipe_run_params
            )
            assert get_log_context() == LogContext(request_id="req-live", pipeline_run_id="plr-live")

        ((code, minted_id, context),) = pipe.seen
        assert code == "outer"
        assert minted_id is not None
        assert context == LogContext(request_id="req-live", pipeline_run_id="plr-live", pipe_run_id=minted_id)
        (record,) = _own_records(caplog)
        assert _field(record, name="pipe_run_id") == minted_id
        assert _field(record, name="request_id") == "req-live"
        assert _field(record, name="pipeline_run_id") == "plr-live"

    async def test_a_nested_pipe_binds_its_own_id_and_the_outer_one_comes_back(self, caplog: pytest.LogCaptureFixture) -> None:
        inner = _make_pipe(code="inner")
        outer = _make_pipe(code="outer", nested=inner)
        pipe_run_params = PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10)

        with caplog.at_level(logging.INFO), log.context(pipeline_run_id="plr-live"):
            await outer.live_run_pipe(
                job_metadata=_seam_shaped_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=pipe_run_params
            )

        (outer_code, outer_id, outer_context), (after_code, after_id, after_context) = outer.seen
        ((inner_code, inner_id, inner_context),) = inner.seen
        assert (outer_code, inner_code, after_code) == ("outer", "inner", "outer after nested")
        assert outer_id is not None
        assert inner_id is not None
        assert inner_id != outer_id
        assert after_id == outer_id
        assert outer_context is not None
        assert outer_context.pipe_run_id == outer_id
        assert inner_context is not None
        assert inner_context.pipe_run_id == inner_id
        assert after_context is not None
        assert after_context.pipe_run_id == outer_id
        outer_record, inner_record, back_record = _own_records(caplog)
        assert _field(outer_record, name="pipe_run_id") == outer_id
        assert _field(inner_record, name="pipe_run_id") == inner_id
        assert _field(back_record, name="pipe_run_id") == outer_id
