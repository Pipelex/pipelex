from pathlib import Path
from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.stored_value_prompt.cases import STORED_TEXT, STORED_TEXT_URL, StoredValuePromptCases
from tests.integration.pipelex.pipes.stored_value_prompt.conftest import RecordingContentGenerator


@pytest.mark.asyncio(loop_scope="class")
class TestPipeStructureStoredTextPrompt:
    async def test_the_structuring_prompt_renders_a_stored_source_in_the_leaf(
        self,
        mocker: MockerFixture,
        load_test_library: Callable[[list[Path]], None],
        scoped_job_metadata: JobMetadata,
        recording_content_generator: RecordingContentGenerator,
    ) -> None:
        """PipeStructure takes PipeLLM's path: its prompt crosses unrendered, and the leaf renders the loaded source."""
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_structure")])
        execution_data_spy = mocker.spy(PipeStructure, "_register_execution_data")
        pipe = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_pipe_structure",
            pipe_code="structure_stored_pages",
            blueprint=PipeStructureBlueprint(
                description="Structure pages that live in storage",
                inputs={"draft_text": NativeConceptCode.TEXT},
                output="SimpleResult",
            ),
            concept_codes_from_the_same_domain=["SimpleResult"],
        )
        get_pipe_library().add_new_pipe(pipe)
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent.model_validate(StoredValuePromptCases.TEXT_REFERENCE),
                name="draft_text",
            ),
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            job_metadata=scoped_job_metadata,
            working_memory=working_memory,
        )
        await get_pipe_router().run(pipe_job=pipe_job)

        assert len(recording_content_generator.crossed_prompts) == 1
        crossed_prompt = recording_content_generator.crossed_prompts[0]
        assert crossed_prompt.entry_point == "make_object"
        assert STORED_TEXT_URL in crossed_prompt.wire_dump
        assert STORED_TEXT not in crossed_prompt.wire_dump
        assert crossed_prompt.nb_unloaded_stored_values == 1
        assert crossed_prompt.context_names == {"text"}

        execution_data: dict[str, Any] = execution_data_spy.call_args.kwargs["execution_data"]
        rendered_user_prompt = execution_data["rendered_user_prompt"]
        assert isinstance(rendered_user_prompt, str)
        assert rendered_user_prompt.startswith("Read the following text carefully and produce the requested structured output from it.")
        assert f"---\n{STORED_TEXT}" in rendered_user_prompt
