from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept, get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_structure.test_structures_basic import SimpleResult


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPreliminaryTextE2E:
    """End-to-end test for the `structuring_method = preliminary_text` elaboration path.

    The MTHDS fixture declares a single PipeLLM with `structuring_method = "preliminary_text"`.
    BundleElaborator rewrites it into a wrapping PipeSequence + a draft PipeLLM + a
    PipeStructure. We then run the user-facing pipe (the wrapping sequence) and assert
    the final output is an instance of the target structured concept.
    """

    async def test_preliminary_text_runs_through_elaborated_pipes(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])

        user_facing_pipe = get_required_pipe(pipe_code="make_simple_result")
        assert isinstance(user_facing_pipe, PipeSequence)
        assert len(user_facing_pipe.sequential_sub_pipes) == 2
        assert user_facing_pipe.sequential_sub_pipes[0].pipe_code == "make_simple_result__draft_text"
        assert user_facing_pipe.sequential_sub_pipes[1].pipe_code == "make_simple_result__structure"

        structure_step = get_required_pipe(pipe_code="make_simple_result__structure")
        assert isinstance(structure_step, PipeStructure)

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="Pipelex"),
                name="topic",
            ),
        )
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=user_facing_pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)
        pretty_print(pipe_output, title="preliminary_text e2e output")

        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.working_memory.get_stuff("draft_text") is not None
        if pipe_run_mode.is_live:
            assert pipe_output.main_stuff.concept.code == "SimpleResult"
            assert isinstance(pipe_output.main_stuff.content, SimpleResult)
            assert pipe_output.main_stuff.content.title
            assert isinstance(pipe_output.main_stuff.content.score, int)
