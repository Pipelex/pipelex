"""``live_run_pipe`` binds the pipe run's own id onto the log context for the whole of the pipe's run.

The job metadata a submission builds carries no ``pipe_run_id``; the pipe mints one as it starts and
hands it down on a metadata copy. The binding here is what makes every record emitted during a pipe's
run name the run it belongs to: the line announcing it, the records of its body, its span hooks and
its failure alike. A nested pipe rebinds its own and the outer one comes back when it returns, however
it returns. A pipe lifted for absent optional inputs has no run and no id, so its skip line is not in
scope here. It is the binding every orchestration shares, so it lives on the pipe and not on the runner.
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
    """What a recording pipe saw at one moment of its run: the moment, the metadata's pipe_run_id if any, and the bound context."""

    moment: str
    pipe_run_id: str | None
    context: LogContext | None


class RecordingPipe(PipeAbstract):
    """A pipe whose live run and span hooks record the context they see; it may run a nested pipe, and it may fail."""

    pipe_category: Any = "PipeOperator"
    type: Any = "PipeFunc"
    nested: RecordingPipe | None = None
    fails: bool = False
    seen: list[Seen] = Field(default_factory=empty_list_factory_of(Seen))

    def _see(self, *, moment: str, job_metadata: JobMetadata | None = None) -> None:
        pipe_run_id = job_metadata.pipe_run_id if job_metadata is not None else None
        self.seen.append(Seen(moment=f"{self.code} {moment}", pipe_run_id=pipe_run_id, context=get_log_context()))

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
        self._see(moment="running", job_metadata=job_metadata)
        log.info(f"inside {self.code}")
        if self.fails:
            msg = f"{self.code} failed"
            raise RuntimeError(msg)
        if self.nested is not None:
            await self.nested.live_run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
            )
            self._see(moment="after nested", job_metadata=job_metadata)
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

    @override
    def _end_pipe_span_success(self, span: Any, *, pipe_output: PipeOutput, is_root_span: bool) -> None:
        self._see(moment="succeeded")

    @override
    def _end_pipe_span_error(self, span: Any, *, error: BaseException, is_root_span: bool = False) -> None:
        self._see(moment="failed")
        log.info(f"{self.code} span ends in error")


def _make_pipe(*, code: str, nested: RecordingPipe | None = None, fails: bool = False) -> RecordingPipe:
    return RecordingPipe(
        code=code,
        domain_code="test_log_context",
        description=code,
        output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
        nested=nested,
        fails=fails,
        seen=[],
    )


def _live_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10)


def _seam_shaped_metadata() -> JobMetadata:
    """What a submission builds: the run's identifiers, and no pipe_run_id yet."""
    return JobMetadata(run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", pipeline_run_id="plr-live", request_id="req-live"))


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == __name__]


def _announcements(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The lines ``live_run_pipe`` itself emits to announce each pipe, on the pipe machinery's own logger."""
    return [record for record in caplog.records if record.name == PipeAbstract.__module__ and record.levelno == logging.INFO]


def _field(record: logging.LogRecord, *, name: str) -> Any:
    """A field carried on the record: an attribute the stdlib does not declare, read the way a sink reads it."""
    return getattr(record, name)


def _pipe_run_ids(seen: list[Seen]) -> list[str | None]:
    return [entry.context.pipe_run_id if entry.context is not None else None for entry in seen]


@pytest.mark.asyncio
class TestLiveRunPipeLogContext:
    async def test_the_minted_pipe_run_id_is_bound_for_the_whole_pipe_and_released_after(self, caplog: pytest.LogCaptureFixture) -> None:
        pipe = _make_pipe(code="outer")

        with caplog.at_level(logging.INFO), log.context(request_id="req-live", pipeline_run_id="plr-live"):
            await pipe.live_run_pipe(
                job_metadata=_seam_shaped_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=_live_params()
            )
            assert get_log_context() == LogContext(request_id="req-live", pipeline_run_id="plr-live")

        running, succeeded = pipe.seen
        assert (running.moment, succeeded.moment) == ("outer running", "outer succeeded")
        minted_id = running.pipe_run_id
        assert minted_id is not None
        assert running.context == LogContext(request_id="req-live", pipeline_run_id="plr-live", pipe_run_id=minted_id)
        assert succeeded.context == running.context
        (announcement,) = _announcements(caplog)
        assert _field(announcement, name="pipe_run_id") == minted_id
        (record,) = _own_records(caplog)
        assert _field(record, name="pipe_run_id") == minted_id
        assert _field(record, name="request_id") == "req-live"
        assert _field(record, name="pipeline_run_id") == "plr-live"

    async def test_a_nested_pipe_binds_its_own_id_and_the_outer_one_comes_back(self, caplog: pytest.LogCaptureFixture) -> None:
        inner = _make_pipe(code="inner")
        outer = _make_pipe(code="outer", nested=inner)

        with caplog.at_level(logging.INFO), log.context(pipeline_run_id="plr-live"):
            await outer.live_run_pipe(
                job_metadata=_seam_shaped_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=_live_params()
            )

        outer_id = outer.seen[0].pipe_run_id
        inner_id = inner.seen[0].pipe_run_id
        assert outer_id is not None
        assert inner_id is not None
        assert inner_id != outer_id
        assert [entry.moment for entry in outer.seen] == ["outer running", "outer after nested", "outer succeeded"]
        assert _pipe_run_ids(outer.seen) == [outer_id, outer_id, outer_id]
        assert [entry.moment for entry in inner.seen] == ["inner running", "inner succeeded"]
        assert _pipe_run_ids(inner.seen) == [inner_id, inner_id]
        outer_announcement, inner_announcement = _announcements(caplog)
        assert _field(outer_announcement, name="pipe_run_id") == outer_id
        assert _field(inner_announcement, name="pipe_run_id") == inner_id
        outer_record, inner_record, back_record = _own_records(caplog)
        assert _field(outer_record, name="pipe_run_id") == outer_id
        assert _field(inner_record, name="pipe_run_id") == inner_id
        assert _field(back_record, name="pipe_run_id") == outer_id

    async def test_a_failing_pipe_keeps_its_own_id_through_its_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        inner = _make_pipe(code="inner", fails=True)
        outer = _make_pipe(code="outer", nested=inner)

        with caplog.at_level(logging.INFO), log.context(pipeline_run_id="plr-live"):
            with pytest.raises(RuntimeError, match="inner failed"):
                await outer.live_run_pipe(
                    job_metadata=_seam_shaped_metadata(), working_memory=WorkingMemoryFactory.make_empty(), pipe_run_params=_live_params()
                )
            assert get_log_context() == LogContext(pipeline_run_id="plr-live")

        outer_id = outer.seen[0].pipe_run_id
        inner_id = inner.seen[0].pipe_run_id
        assert outer_id is not None
        assert inner_id is not None
        assert [entry.moment for entry in inner.seen] == ["inner running", "inner failed"]
        assert _pipe_run_ids(inner.seen) == [inner_id, inner_id]
        assert [entry.moment for entry in outer.seen] == ["outer running", "outer failed"]
        assert _pipe_run_ids(outer.seen) == [outer_id, outer_id]
        outer_record, inner_record, inner_error, outer_error = _own_records(caplog)
        assert _field(outer_record, name="pipe_run_id") == outer_id
        assert _field(inner_record, name="pipe_run_id") == inner_id
        assert inner_error.getMessage() == "inner span ends in error"
        assert _field(inner_error, name="pipe_run_id") == inner_id
        assert outer_error.getMessage() == "outer span ends in error"
        assert _field(outer_error, name="pipe_run_id") == outer_id
