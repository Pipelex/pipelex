from pathlib import Path
from typing import Callable, cast

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
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
class TestPipeStructureInBatch:
    """PipeBatch iterating PipeStructure over a list of texts."""

    async def test_batch_with_pipe_structure(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])
        domain_code = "test_pipe_structure"

        structure_blueprint = PipeStructureBlueprint(
            description="Structure draft text into a SimpleResult",
            inputs={"draft_item": NativeConceptCode.TEXT},
            output="SimpleResult",
        )
        structure_pipe = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="structure_one_simple_result",
            blueprint=structure_blueprint,
            concept_codes_from_the_same_domain=["SimpleResult"],
        )
        get_pipe_library().add_new_pipe(structure_pipe)

        batch_blueprint = PipeBatchBlueprint(
            description="Run PipeStructure over a list of draft texts",
            branch_pipe_code="structure_one_simple_result",
            inputs={"draft_texts": NativeConceptCode.TEXT},
            output="SimpleResult",
            input_list_name="draft_texts",
            input_item_name="draft_item",
        )
        batch_pipe = PipeFactory[PipeBatch].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="batch_structure_simple_results",
            blueprint=batch_blueprint,
            concept_codes_from_the_same_domain=["SimpleResult"],
        )
        get_pipe_library().add_new_pipe(batch_pipe)

        draft_items = [
            TextContent(text="Title 'Alpha' got a score of 7."),
            TextContent(text="Title 'Beta' got a score of 8."),
            TextContent(text="Title 'Gamma' got a score of 9."),
        ]
        list_stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=ListContent[StuffContent](items=cast("list[StuffContent]", draft_items)),
            name="draft_texts",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(list_stuff)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=batch_pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name="batch_result",
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        pretty_print(pipe_output, title="batch with PipeStructure output")
        assert pipe_output is not None
        assert pipe_output.main_stuff is not None
        assert pipe_output.working_memory.get_stuff("batch_result") is not None
        result_list = pipe_output.main_stuff_as_list(item_type=StuffContent)
        assert len(result_list.items) == 3
        if pipe_run_mode.is_live:
            for item in result_list.items:
                assert isinstance(item, SimpleResult)
                assert item.title
                assert isinstance(item.score, int)
