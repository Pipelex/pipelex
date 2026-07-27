from pathlib import Path
from typing import Callable

import pytest

from pipelex import log, pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeStructure:
    async def test_pipe_structure_simple(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ) -> None:
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])
        blueprint = PipeStructureBlueprint(
            description="Structure a draft text into a SimpleResult",
            inputs={"draft_text": NativeConceptCode.TEXT},
            output="SimpleResult",
        )
        pipe = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_pipe_structure",
            pipe_code="adhoc_for_test_pipe_structure",
            blueprint=blueprint,
            concept_codes_from_the_same_domain=["SimpleResult"],
        )
        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe)

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text="A book titled 'The Pipelex Way' with a score of 9."),
                name="draft_text",
            ),
        )
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=working_memory,
        )
        pipe_output = await get_pipe_router().run(pipe_job=pipe_job)

        log.verbose(pipe_output, title="stuff")
        pretty_print(pipe_output.main_stuff, title="structured_output")
