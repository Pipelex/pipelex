from pathlib import Path
from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.pipes.operator.pipe_structure.test_structures_basic import SimpleResult


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeStructureInSequence:
    """Hand-authored PipeSequence wrapping a PipeLLM + PipeStructure (no elaboration sugar)."""

    async def test_sequence_with_pipe_structure(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])
        domain_code = "test_pipe_structure_seq"

        # The structuring step is authored explicitly here — no preliminary_text elaboration is involved,
        # so this test covers the path where users compose PipeStructure into a PipeSequence by hand.
        structure_blueprint = PipeStructureBlueprint(
            description="Turn the draft text into a SimpleResult",
            inputs={"draft_text": NativeConceptCode.TEXT},
            output="SimpleResult",
        )
        structure_pipe = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="structure_simple_result",
            blueprint=structure_blueprint,
            concept_codes_from_the_same_domain=["SimpleResult"],
        )
        get_pipe_library().add_new_pipe(structure_pipe)

        sequence_blueprint = PipeSequenceBlueprint(
            description="Draft text via PipeLLM, then structure via PipeStructure",
            inputs={"topic": NativeConceptCode.TEXT},
            output="SimpleResult",
            steps=[
                SubPipeBlueprint(pipe="write_draft_about_topic", result="draft_text"),
                SubPipeBlueprint(pipe="structure_simple_result", result="result"),
            ],
        )
        sequence_pipe = PipeFactory[PipeSequence].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="text_then_structure_sequence",
            blueprint=sequence_blueprint,
            concept_codes_from_the_same_domain=["SimpleResult"],
        )
        get_pipe_library().add_new_pipe(sequence_pipe)
        assert len(sequence_pipe.sequential_sub_pipes) == 2

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="The book 'The Pipelex Way' deserves a score of 9 out of 10."),
                name="topic",
            ),
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=sequence_pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        pretty_print(pipe_output, title="sequence with PipeStructure output")
        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.working_memory.get_stuff("draft_text") is not None
        assert pipe_output.working_memory.get_stuff("result") is not None
        if pipe_run_mode.is_live:
            assert isinstance(pipe_output.main_stuff.content, SimpleResult)
            assert pipe_output.main_stuff.content.title
            assert isinstance(pipe_output.main_stuff.content.score, int)
