"""An interpreted pipe's log lines are unchanged by the kernel binding its own step.

Every kernel function that takes a ``job_metadata`` binds it (``test_kernel_log_context.py``). Inside
the interpreter that binding nests within the one ``live_run_pipe`` opened, so it must be a no-op: the
operator has to hand the kernel metadata carrying the very ``pipe_run_id`` that ``live_run_pipe``
minted and bound. This pins that equality on ``PipeLLM``, so that if it ever hands the kernel a copy
with an id of its own, it goes red here instead of silently re-attributing its lines to a step nobody
announced. The other kernel-backed operators hand down their metadata the same way and are not pinned
here.

The pipe runs in LIVE through ``live_run_pipe`` itself. Two observers sit on the path: a spy on the
operator's call into ``run_llm_text``, which records the metadata the operator hands down and the
binding around the call, and a probe standing in for the content generator, which records the binding
the kernel leaves in place when it reaches the generation. The probe answers the generation, so
nothing reaches a provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import pytest

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.kernel import llm_ops
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.pipeline_factory import PipelineFactory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.log.log_context import LogContext, get_log_context

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.kernel.llm_results import LlmTextResult

MINTED_PIPE_RUN_ID = "pr-minted-by-live-run-pipe"
PIPELINE_RUN_ID = "plr-interpreted"
REQUEST_ID = "req-interpreted"


class ContentGeneratorProbe:
    """Answers the text generation and records the log context bound when the kernel reaches it."""

    def __init__(self) -> None:
        self.seen: list[LogContext | None] = []

    async def make_llm_text(self, **kwargs: Any) -> str:  # ruff: ignore[unused-method-argument]
        self.seen.append(get_log_context())
        return "generated text"


class KernelCallSpy:
    """Wraps the operator's call into ``run_llm_text``: records what it was handed and what was bound, then delegates."""

    def __init__(self) -> None:
        self.handed_pipe_run_ids: list[str | None] = []
        self.bound: list[LogContext | None] = []

    async def __call__(self, **kwargs: Any) -> LlmTextResult:
        job_metadata: JobMetadata = kwargs["job_metadata"]
        self.handed_pipe_run_ids.append(job_metadata.pipe_run_id)
        self.bound.append(get_log_context())
        return await llm_ops.run_llm_text(**kwargs)


def _make_pipe() -> PipeLLM:
    blueprint = PipeLLMBlueprint(
        description="log-context test pipe",
        output="native.Text",
        prompt="Say something.",
    )
    return PipeFactory[PipeLLM].make_from_blueprint(domain_code="test_log_context", pipe_code="say_something", blueprint=blueprint)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMLogContext:
    async def test_the_kernel_is_handed_and_binds_the_id_live_run_pipe_minted(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        mocker.patch.object(PipelineFactory, "make_pipe_run_id", return_value=MINTED_PIPE_RUN_ID)
        probe = ContentGeneratorProbe()
        mocker.patch.object(llm_ops, "get_content_generator", return_value=probe)
        spy = KernelCallSpy()
        mocker.patch("pipelex.pipe_operators.llm.pipe_llm.run_llm_text", new=spy)
        job_metadata = JobMetadata(
            run_metadata=RunMetadata(
                user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id=PIPELINE_RUN_ID, request_id=REQUEST_ID
            ),
        )
        expected = LogContext(request_id=REQUEST_ID, pipeline_run_id=PIPELINE_RUN_ID, pipe_run_id=MINTED_PIPE_RUN_ID)

        # The run-level binding `PipeRun.run` opens around a direct-mode run.
        with job_metadata.log_context():
            await _make_pipe().live_run_pipe(
                job_metadata=job_metadata,
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10),
            )

        assert spy.handed_pipe_run_ids == [MINTED_PIPE_RUN_ID], (
            "the operator must hand the kernel the pipe run id `live_run_pipe` minted — a fresh one would make the "
            "kernel's own binding re-attribute the step's lines to a pipe run nobody announced"
        )
        assert spy.bound == [expected]
        assert probe.seen == [expected], "the kernel's nested binding must leave the interpreter's context exactly as it was"
        assert get_log_context() is None
