from pathlib import Path
from typing import Callable

import pytest

from pipelex import log, pretty_print
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry, get_native_concept, get_pipe_library, get_pipe_router
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint, StructuringMethod
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.test_data import BasicStructuredDataTestCases, PipeTestCases


@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeLLMBasic:
    async def test_pipe_llm_simple(
        self,
        job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_llm")])
        pipe_llm_blueprint = PipeLLMBlueprint(
            description="LLM test for basic text generation",
            output=NativeConceptCode.TEXT,
            system_prompt=PipeTestCases.SYSTEM_PROMPT,
            prompt=PipeTestCases.USER_PROMPT,
        )
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="documents",
            pipe_code="adhoc_for_test_pipe_llm",
            blueprint=pipe_llm_blueprint,
        )
        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
        )
        pipe_llm_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )

        log.verbose(pipe_llm_output, title="stuff")
        llm_generated_text = pipe_llm_output.main_stuff_as_text
        pretty_print(llm_generated_text, title="llm_generated_text")

    @pytest.mark.parametrize(
        ("topic", "data", "concept"),
        BasicStructuredDataTestCases.STRUCTURE_TEST_CASES,
        # + ComplexStructuredDataTestCases.STRUCTURE_TEST_CASES,
    )
    @pytest.mark.parametrize(
        "structuring_method",
        [
            # StructuringMethod.DIRECT,
            StructuringMethod.PRELIMINARY_TEXT,
        ],
    )
    @pytest.mark.parametrize(
        ("llm", "llm_to_structure"),
        [
            ("gpt-4o-mini", "gpt-4o-mini"),
            # ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
            # ("gemini-2.5-flash-lite", "gpt-4o-mini"),
        ],
    )
    async def test_pipe_llm_structured(
        self,
        job_metadata: JobMetadata,
        topic: str,
        data: str,
        concept: str,
        structuring_method: StructuringMethod,
        pipe_run_mode: PipeRunMode,
        llm: str,
        llm_to_structure: str,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_llm")])
        # TODO: Add assertion on generated objects vs expected results
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_native_concept(NativeConceptCode.TEXT),
                content=TextContent(text=data),
                name="data",
            ),
        )

        # Create pipe blueprint
        pipe_llm_blueprint = PipeLLMBlueprint(
            description=f"Extract {concept} from text",
            inputs={"data": "Text"},
            output=f"test_structured_generations.{concept}",
            prompt=BasicStructuredDataTestCases.EXTRACTION_PROMPT,
            model=llm,
            model_to_structure=llm_to_structure,
            structuring_method=structuring_method,
        )

        pretty_print(pipe_llm_blueprint, title="pipe_llm_blueprint")
        pipe_code = f"extract_{topic}_{concept}_{structuring_method}"
        pipe_code = pipe_code.lower().replace(" ", "_")
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_structured_generations",
            pipe_code=pipe_code,
            blueprint=pipe_llm_blueprint,
        )
        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe)

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=pipe,
            working_memory=working_memory,
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
        )

        pipe_llm_output = await get_pipe_router().run(pipe_job=pipe_job)

        pretty_print(pipe_llm_output, title="pipe_llm_dzqdzqoutput")

        # Log test information
        log.verbose(f"Testing {topic} with {structuring_method} method", title="Test Case")

        # Get the main output
        main_stuff = pipe_llm_output.main_stuff
        assert main_stuff is not None, f"No output generated for {topic}"

        # Pretty print the structured output
        pretty_print(main_stuff.content, title=f"{topic} - {concept} - {structuring_method}")

        # Verify the output type matches expected structure
        structure_class = get_class_registry().get_class(concept)
        assert structure_class is not None, f"Structure class {concept} not found in registry"
        assert isinstance(main_stuff.content, structure_class), (
            f"Output content is not of expected type {concept}. Got {type(main_stuff.content).__name__} instead."
        )

    @pytest.mark.llm
    @pytest.mark.inference
    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(("stuff", "attribute_paths"), PipeTestCases.STUFFS_IMAGE_ATTRIBUTES)
    async def test_pipe_llm_attribute_image(
        self,
        job_metadata: JobMetadata,
        stuff: Stuff,
        attribute_paths: list[str],
        pipe_run_mode: PipeRunMode,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/operator/pipe_llm")])
        for attribute_path in attribute_paths:
            stuff_name = attribute_path
            if not stuff_name:
                pytest.fail(f"Cannot use nameless stuff in this test: {stuff}")
            working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)
            # Build prompt dynamically to include the input variable reference
            prompt_with_input = f"Here is the input: ${stuff_name}\n{PipeTestCases.MULTI_IMG_DESC_PROMPT}"
            pipe_llm_blueprint = PipeLLMBlueprint(
                description="LLM test for image processing with attributes",
                inputs={stuff_name: "native.Image"},
                output=NativeConceptCode.TEXT,
                system_prompt=PipeTestCases.SYSTEM_PROMPT,
                prompt=prompt_with_input,
            )
            pipe_job = PipeJobFactory.make_pipe_job(
                working_memory=working_memory,
                pipe=PipeFactory[PipeLLM].make_from_blueprint(
                    domain_code="generic",
                    pipe_code="adhoc_for_test_pipe_llm_image",
                    blueprint=pipe_llm_blueprint,
                ),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
                job_metadata=job_metadata,
            )

            pipe_llm_output = await get_pipe_router().run(
                pipe_job=pipe_job,
            )

            log.verbose(pipe_llm_output, title="stuff")
            _ = pipe_llm_output.main_stuff_as_text
