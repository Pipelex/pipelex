"""A `PipeStructure` step whose model's answer does not fit names the model and the concept the step declares."""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from tests.helpers.schema_mismatch import WORKER_MODEL, assert_names_model_and_concept, make_job_metadata, make_rendered_schema_mismatch


class TestPipeStructureSchemaMismatch:
    @pytest.mark.asyncio
    async def test_the_structured_answer_names_the_concept(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.structure.pipe_structure.generate_object_content", side_effect=make_rendered_schema_mismatch())
        blueprint = PipeStructureBlueprint(description="Read the parcel's weight", inputs={"draft_text": "native.Text"}, output="native.Number")
        pipe_structure = PipeFactory[PipeStructure].make_from_blueprint(domain_code="schema_mismatch", pipe_code="read_weight", blueprint=blueprint)
        source = StuffFactory.make_stuff(
            get_native_concept(native_concept=NativeConceptCode.TEXT), content=TextContent(text="The parcel weighs 7 kg."), name="draft_text"
        )

        with pytest.raises(PipeRunError) as exc_info:
            await pipe_structure._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
                job_metadata=make_job_metadata(),
                working_memory=WorkingMemoryFactory.make_from_single_stuff(source),
                pipe_run_params=PipeRunParamsFactory.make_run_params(),
            )

        assert_names_model_and_concept(failure=exc_info.value, model=WORKER_MODEL, concept="native.Number")
