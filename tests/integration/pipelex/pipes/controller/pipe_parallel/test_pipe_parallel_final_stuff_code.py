"""PipeParallel honors a requested final_stuff_code on its combined output stuff.

When a PipeParallel runs as the branch pipe of a PipeBatch, the batch pre-allocates a stuff code
for each branch's final output so the aggregated list items keep their graph identity. The parallel
must stamp that code on its COMBINED stuff (like operators do on theirs), not discard it — and must
NOT leak it onto the branch outputs.
"""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_factory import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode

_REQUESTED_CODE = "requested-final-stuff-code"


@pytest.mark.asyncio(loop_scope="class")
class TestPipeParallelFinalStuffCode:
    async def test_combined_stuff_carries_requested_final_stuff_code(
        self, job_metadata: JobMetadata, load_test_library: Callable[[list[Path]], None]
    ):
        """A dry run is enough: stamping the combined stuff is mode-independent (shared combine helper)."""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_parallel")])
        pipe_parallel_blueprint = PipeParallelBlueprint(
            description="Parallel honoring final_stuff_code",
            inputs={"input_text": f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}"},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.COMPOSITE}",
            branches=[
                SubPipeBlueprint(pipe="analyze_sentiment", result="sentiment_result"),
                SubPipeBlueprint(pipe="count_words", result="word_count_result"),
            ],
            add_each_output=True,
        )
        pipe_parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code="test_integration",
            pipe_code="parallel_with_final_code",
            blueprint=pipe_parallel_blueprint,
        )

        input_text_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="A short text to analyze."),
            name="input_text",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(input_text_stuff)

        pipe_run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY)
        pipe_run_params.final_stuff_code = _REQUESTED_CODE

        pipe_output = await pipe_parallel.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            output_name="parallel_results",
            pipe_run_params=pipe_run_params,
        )

        main_stuff = pipe_output.main_stuff
        assert main_stuff.stuff_code == _REQUESTED_CODE, "the combined stuff must carry the requested final_stuff_code"

        # The requested code applies to the combined stuff only — branch outputs keep their own codes.
        final_working_memory = pipe_output.working_memory
        assert final_working_memory.get_stuff("sentiment_result").stuff_code != _REQUESTED_CODE
        assert final_working_memory.get_stuff("word_count_result").stuff_code != _REQUESTED_CODE
