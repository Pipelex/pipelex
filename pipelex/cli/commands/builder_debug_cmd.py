import asyncio
from typing import Any, List

import typer

from pipelex import log, pretty_print
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes
from pipelex.core.stuffs.stuff_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_concept_provider, get_report_delegate
from pipelex.libraries.pipelines.builder.builder import DomainInformation, PipelexBundleSpec
from pipelex.libraries.pipelines.builder.concept.concept_spec import (
    ConceptSpec,
    ConceptStructureSpec,
    ConceptStructureSpecFieldType,
)
from pipelex.libraries.pipelines.builder.pipe.pipe_condition_spec import PipeConditionPipeMapSpec, PipeConditionSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSignature
from pipelex.libraries.pipelines.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

builder_debug_app = typer.Typer(help="Debug and test intermediate steps of the builder pipeline", no_args_is_help=True)


def _get_example_concept_specs() -> List[ConceptSpec]:
    """Get hardcoded example concept specs for testing."""
    return [
        ConceptSpec(
            the_concept_code="TaskDescription",
            definition="A description of a task that needs to be completed",
            structure="{ 'title': 'str', 'description': 'str', 'priority': 'str', 'due_date': 'Optional[datetime]' }",
        ),
        ConceptSpec(
            the_concept_code="TaskResult",
            definition="The result of completing a task",
            structure="{ 'task_id': 'str', 'status': 'str', 'completion_notes': 'str', 'completed_at': 'datetime' }",
        ),
        ConceptSpec(
            the_concept_code="UserProfile",
            definition="A user profile containing personal information",
            structure="{ 'name': 'str', 'email': 'str', 'role': 'str', 'preferences': 'Dict[str, Any]' }",
        ),
    ]


def _get_example_pipe_signatures() -> list[PipeSignature]:
    """Get hardcoded example pipe signatures for testing."""

    concept_specs = _get_example_concept_specs()

    # Create concept spec lookup
    concept_lookup = {spec.the_concept_code: spec for spec in concept_specs}

    return [
        PipeSignature(
            result="analyze_task",
            category=AllowedPipeCategories.PIPE_OPERATOR,
            code="analyze_task",
            type=AllowedPipeTypes.PIPE_LLM,
            definition="Analyze a task description and extract key information",
            inputs={"task_description": concept_lookup["TaskDescription"]},
            output=concept_lookup["TaskResult"],
        ),
        PipeSignature(
            result="process_user_request",
            category=AllowedPipeCategories.PIPE_OPERATOR,
            code="process_user_request",
            type=AllowedPipeTypes.PIPE_SEQUENCE,
            definition="Process a user request by analyzing the task and generating a result",
            inputs={
                "task_description": concept_lookup["TaskDescription"],
                "user_profile": concept_lookup["UserProfile"],
            },
            output=concept_lookup["TaskResult"],
        ),
        PipeSignature(
            result="validate_task_completion",
            category=AllowedPipeCategories.PIPE_OPERATOR,
            code="validate_task_completion",
            type=AllowedPipeTypes.PIPE_CONDITION,
            definition="Validate if a task has been completed successfully based on status",
            inputs={"task_result": concept_lookup["TaskResult"]},
            output=concept_lookup["TaskResult"],
        ),
    ]


@builder_debug_app.command("build-concepts")
def build_concepts_cmd() -> None:
    """Run the build_concept_blueprint step with hardcoded example data."""
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)

    log.info("Starting build_concept_blueprint step...")

    concept_specs = _get_example_concept_specs()

    async def run_build_concepts() -> None:
        for i, concept_spec in enumerate(concept_specs):
            log.info(f"Processing concept {i + 1}/{len(concept_specs)}: {concept_spec.the_concept_code}")

            # Run the build_concept_blueprint pipe for each concept spec
            pipe_output = await execute_pipeline(
                pipe_code="build_concept_blueprint",
                input_memory={
                    "concept_spec": concept_spec,
                },
            )

            log.info(f"Successfully processed concept: {concept_spec.the_concept_code}")
            pretty_print(pipe_output.main_stuff, title=f"Concept Blueprint for {concept_spec.the_concept_code}")

    asyncio.run(run_build_concepts())

    # Display cost report
    get_report_delegate().generate_report()
    log.info("build_concept_blueprint step completed successfully!")


@builder_debug_app.command("create-pipes")
def create_pipes_cmd() -> None:
    """Run the create_pipes_from_signatures step with hardcoded example data."""
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)

    log.info("Starting create_pipes_from_signatures step...")

    concept_specs = _get_example_concept_specs()
    pipe_signatures = _get_example_pipe_signatures()

    async def run_create_pipes() -> None:
        # First, build concept blueprints
        log.info("Building concept blueprints first...")
        concept_spec_blueprints: list[Any] = []

        for concept_spec in concept_specs:
            pipe_output = await execute_pipeline(
                pipe_code="build_concept_blueprint",
                input_memory={
                    "concept_spec": concept_spec,
                },
            )
            concept_spec_blueprints.append(pipe_output.main_stuff)

        # Now create pipes from signatures
        log.info("Creating pipes from signatures...")
        for i, pipe_signature in enumerate(pipe_signatures):
            log.info(f"Processing pipe {i + 1}/{len(pipe_signatures)}: {pipe_signature.code}")

            # Create list content for concept spec blueprints

            concept_blueprints_list: ListContent[Any] = ListContent(items=[stuff.content for stuff in concept_spec_blueprints])

            # Run the create_pipes_from_signatures pipe
            pipe_output = await execute_pipeline(
                pipe_code="create_pipes_from_signatures",
                input_memory={
                    "pipe_signature": pipe_signature,
                    "concept_spec_blueprints": concept_blueprints_list,
                },
            )

            log.info(f"Successfully processed pipe: {pipe_signature.code}")
            pretty_print(pipe_output.main_stuff, title=f"Pipe Blueprint for {pipe_signature.code}")

    asyncio.run(run_create_pipes())

    # Display cost report
    get_report_delegate().generate_report()
    log.info("create_pipes_from_signatures step completed successfully!")


@builder_debug_app.command("full-pipeline")
def full_pipeline_cmd() -> None:
    """Run both build_concept_blueprint and create_pipes_from_signatures steps in sequence."""
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)

    log.info("Starting full intermediate pipeline test...")

    concept_specs = _get_example_concept_specs()
    pipe_signatures = _get_example_pipe_signatures()

    async def run_full_pipeline() -> None:
        # Step 1: Build concept blueprints
        log.info("Step 1: Building concept blueprints...")
        concept_spec_blueprints: list[Any] = []

        for i, concept_spec in enumerate(concept_specs):
            log.info(f"Building concept {i + 1}/{len(concept_specs)}: {concept_spec.the_concept_code}")

            pipe_output = await execute_pipeline(
                pipe_code="build_concept_blueprint",
                input_memory={
                    "concept_spec": concept_spec,
                },
            )
            concept_spec_blueprints.append(pipe_output.main_stuff)
            log.info(f"✓ Completed concept: {concept_spec.the_concept_code}")

        # Step 2: Create pipes from signatures
        log.info("Step 2: Creating pipes from signatures...")
        pipe_spec_blueprints: list[Any] = []

        # Create list content for concept spec blueprints

        concept_blueprints_list: ListContent[Any] = ListContent(items=[stuff.content for stuff in concept_spec_blueprints])

        for i, pipe_signature in enumerate(pipe_signatures):
            log.info(f"Creating pipe {i + 1}/{len(pipe_signatures)}: {pipe_signature.code}")

            pipe_output = await execute_pipeline(
                pipe_code="create_pipes_from_signatures",
                input_memory={
                    "pipe_signature": pipe_signature,
                    "concept_spec_blueprints": concept_blueprints_list,
                },
            )
            pipe_spec_blueprints.append(pipe_output.main_stuff)
            log.info(f"✓ Completed pipe: {pipe_signature.code}")

        # Summary
        log.info("\n" + "=" * 60)
        log.info("PIPELINE EXECUTION SUMMARY")
        log.info("=" * 60)
        log.info(f"Concepts processed: {len(concept_spec_blueprints)}")
        for i, concept_spec in enumerate(concept_specs):
            log.info(f"  {i + 1}. {concept_spec.the_concept_code}")

        log.info(f"\nPipes processed: {len(pipe_spec_blueprints)}")
        for i, pipe_signature in enumerate(pipe_signatures):
            log.info(f"  {i + 1}. {pipe_signature.code} ({pipe_signature.type})")

        log.info("\nAll intermediate steps completed successfully!")

    asyncio.run(run_full_pipeline())

    # Display cost report
    get_report_delegate().generate_report()


# Example usage: pipelex builder-debug parallel-draft-to-specs
@builder_debug_app.command("parallel-draft-to-specs")
def parallel_draft_to_specs_cmd() -> None:
    """Run the parallel_draft_to_specs step with hardcoded photo opposite brief and plan draft."""
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)

    log.info("Starting parallel_draft_to_specs step...")

    # Hardcoded brief and plan draft
    brief = "Take a photo as input, analyze its content and its most important feature, "
    "imagine the opposite to that feature, render it as a photo"

    plan_draft = """**Main Pipeline: Sequence**
The main pipeline is a PipeSequence that orchestrates the entire process of analyzing a photo and creating its opposite.

**Step 1: Analyze Image Content**
- Pipe Type: PipeLLM (vision-enabled)
- Purpose: Analyze the input photo to identify and describe its content comprehensively
- Inputs: 
  - "input_image": The original photo provided by the user
- Outputs:
  - "image_analysis": A detailed text description of what the image contains, including objects, scenes, colors, mood, and composition

**Step 2: Identify Most Important Feature**
- Pipe Type: PipeLLM
- Purpose: Process the image analysis to determine the single most important or dominant feature in the photo
- Inputs:
  - "image_analysis": The detailed description from Step 1
- Outputs:
  - "important_feature": A text identifying and describing the most prominent characteristic of the image 
  (e.g., "bright sunny day", "crowded urban scene", "calm water surface")

**Step 3: Generate Opposite Concept**
- Pipe Type: PipeLLM
- Purpose: Take the identified important feature and conceptualize its opposite
- Inputs:
  - "important_feature": The dominant feature identified in Step 2
  - "image_analysis": The full analysis from Step 1 (for context)
- Outputs:
  - "opposite_concept": A detailed description of what the opposite would be 
  (e.g., if important feature is "bright sunny day", opposite would be "dark stormy night")

**Step 4: Create Detailed Prompt for Opposite Image**
- Pipe Type: PipeLLM
- Purpose: Transform the opposite concept into a detailed, comprehensive image generation prompt 
that maintains other elements from the original while inverting the key feature
- Inputs:
  - "opposite_concept": The opposite concept from Step 3
  - "image_analysis": The original analysis from Step 1
  - "important_feature": The feature being inverted from Step 2
- Outputs:
  - "image_prompt": A detailed text prompt suitable for image generation, describing the scene with the opposite feature applied

**Step 5: Generate Opposite Image**
- Pipe Type: PipeImgGen
- Purpose: Create a new image based on the detailed prompt that represents the opposite of the original photo's most important feature
- Inputs:
  - "image_prompt": The detailed generation prompt from Step 4
- Outputs:
  - "opposite_image": The final generated image showing the opposite concept rendered as a photo

The sequence executes these five pipes in order, transforming an input photo into its conceptual opposite by first understanding it, identifying its 
key feature, imagining the opposite, and then generating a new image that embodies that opposite while maintaining photographic quality."""

    async def run_parallel_draft_to_specs() -> None:
        # Run the parallel_draft_to_specs pipe
        pipe_output = await execute_pipeline(
            pipe_code="parallel_draft_to_specs",
            input_memory={
                "brief": brief,
                "plan_draft": plan_draft,
            },
        )

        log.info("Successfully processed parallel_draft_to_specs")
        pretty_print(pipe_output, title="Parallel Draft to Specs Result")

    asyncio.run(run_parallel_draft_to_specs())

    # Display cost report
    get_report_delegate().generate_report()
    log.info("parallel_draft_to_specs step completed successfully!")


@builder_debug_app.command("test-compile")
def test_compile_cmd() -> None:
    """Test the compile_in_pipelex_bundle_spec pipe with example data."""
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)

    log.info("Testing compile_in_pipelex_bundle_spec pipe...")

    def _get_example_domain_information():
        return DomainInformation(domain="photo_opposite", definition="A pipeline that takes a photo and generates its visual opposite")

    def _get_example_concept_specs_for_compile():
        """Get the EXACT concept specs that are failing in the full pipeline."""
        return [
            ConceptSpec(
                the_concept_code="PhotoAnalysis",
                definition="Analysis of a photo's visual characteristics and content",
                structure={
                    "dominant_color": ConceptStructureSpec(
                        the_field_name="dominant_color",
                        definition="The primary color that appears most prominently in the photo",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "object_present": ConceptStructureSpec(
                        the_field_name="object_present",
                        definition="A key object or subject identified in the photo",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "mood": ConceptStructureSpec(
                        the_field_name="mood",
                        definition="The emotional tone or atmosphere conveyed by the photo",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "lighting": ConceptStructureSpec(
                        the_field_name="lighting",
                        definition="The type and quality of lighting in the photo",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "composition_style": ConceptStructureSpec(
                        the_field_name="composition_style",
                        definition="The artistic arrangement and framing style of the photo",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                },
                refines=None,
            ),
            ConceptSpec(
                the_concept_code="OppositeDescription",
                definition="Description of the visual opposite concept for image generation",
                structure={
                    "target_color": ConceptStructureSpec(
                        the_field_name="target_color",
                        definition="The primary color that should dominate in the opposite image",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "target_mood": ConceptStructureSpec(
                        the_field_name="target_mood",
                        definition="The emotional tone that should be conveyed in the opposite image",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "target_object": ConceptStructureSpec(
                        the_field_name="target_object",
                        definition="The main object or subject that should appear in the opposite image",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "target_lighting": ConceptStructureSpec(
                        the_field_name="target_lighting",
                        definition="The type of lighting that should be used in the opposite image",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                    "target_composition": ConceptStructureSpec(
                        the_field_name="target_composition",
                        definition="The composition style that should be applied to the opposite image",
                        type=ConceptStructureSpecFieldType.TEXT,
                        required=True,
                        default_value=None,
                    ),
                },
                refines=None,
            ),
        ]

    def _get_example_pipe_specs_for_compile():
        """Get example pipe specs for photo opposite pipeline."""
        from pipelex.libraries.pipelines.builder.pipe.pipe_img_spec import PipeImgGenSpec

        return [
            PipeLLMSpec(
                type="PipeLLM",
                category="PipeOperator",
                definition="""
                Analyzes the input photo using vision LLM capabilities to identify and extract key visual characteristics 
                including dominant colors, lighting conditions, main subjects, 
                composition style, mood, and visual elements that will be used to determine the opposite visual representation.""",
                inputs={"photo": "Image"},
                output="PhotoAnalysis",
                the_pipe_code="analyze_photo",
                system_prompt_template=None,
                system_prompt_template_name=None,
                system_prompt_name=None,
                system_prompt=None,
                prompt_template="""
                Analyze this image in detail. Identify the following characteristics:\n\n1. Dominant colors and color palette\n2.
                 Lighting conditions (bright/dark, warm/cool, natural/artificial)\n3. Main subjects and objects in the scene\n4. 
                 Composition style (centered, rule of thirds, symmetrical, etc.)\n5. Overall mood and atmosphere\n6. Key visual elements 
                 (textures, patterns, shapes)\n7. Background vs foreground elements\n8. Time of day if applicable\n9. Weather conditions 
                 if visible\n10. Artistic style or photographic technique\n\nProvide a comprehensive analysis that captures the essence
                  of this image's visual characteristics.\n\nImage: @photo""",
                template_name=None,
                prompt_name=None,
                prompt=None,
                llm=None,
                llm_to_structure=None,
                structuring_method=None,
                prompt_template_to_structure=None,
                system_prompt_to_structure=None,
                nb_output=None,
                multiple_output=False,
            ),
            PipeLLMSpec(
                type="PipeLLM",
                category="PipeOperator",
                definition="""
                Creates a detailed and comprehensive prompt for image generation that describes the visual opposite of the 
                analyzed photo by inverting colors, lighting, mood, composition, and other visual characteristics to produce a 
                contrasting yet coherent image concept.""",
                inputs={"photo_analysis": "PhotoAnalysis"},
                output="ImgGenPrompt",
                the_pipe_code="generate_opposite_prompt",
                system_prompt_template=None,
                system_prompt_template_name=None,
                system_prompt_name=None,
                system_prompt=None,
                prompt_template="""
                Based on the following photo analysis, create a detailed image generation prompt that describes the visual 
                OPPOSITE of the original image. Invert and contrast the key characteristics:\n\nOriginal Analysis: 
                @photo_analysis\n\nCreate a prompt that:\n1. Uses opposite/complementary colors to the dominant colors\n2. 
                Inverts the lighting (if bright make dark, if warm make cool, etc.)\n3. Changes the mood to the opposite 
                (if cheerful make somber, if calm make energetic, etc.)\n4. Maintains visual coherence while being opposite\n5. 
                Includes specific details about colors, lighting, atmosphere, and style\n6. Describes the scene composition and 
                elements in opposite terms\n\nGenerate a detailed, specific prompt for creating this opposite image:""",
                template_name=None,
                prompt_name=None,
                prompt=None,
                llm=None,
                llm_to_structure=None,
                structuring_method=None,
                prompt_template_to_structure=None,
                system_prompt_to_structure=None,
                nb_output=None,
                multiple_output=False,
            ),
            PipeImgGenSpec(
                type="PipeImgGen",
                category="PipeOperator",
                definition="""
                Generates the opposite image using AI image generation based on the crafted prompt that 
                describes visual characteristics opposite to the original photo, creating a contrasting yet aesthetically coherent result.""",
                inputs={"prompt": "ImgGenPrompt"},
                output="Image",
                the_pipe_code="render_opposite_image",
                img_gen_prompt=None,
                img_gen_prompt_var_name=None,
                img_gen=None,
                aspect_ratio=None,
                is_raw=None,
                seed=None,
                nb_output=1,
                background=None,
                output_format=None,
            ),
            PipeSequenceSpec(
                type="PipeSequence",
                category="PipeController",
                definition="Main pipeline that takes a photo as input and generates its visual opposite through a systematic process \
                    of analyzing the original photo's characteristics, creating an opposite description, and rendering the opposite image. \
                        This pipeline ensures proper sequential execution where each step builds upon the previous one's output.",
                inputs={"photo": "Image"},
                output="Image",
                the_pipe_code="photo_opposite_renderer_main_pipeline",
                steps=[
                    SubPipeSpec(
                        the_pipe_code="analyze_photo", result="photo_analysis", nb_output=None, multiple_output=None, batch_over=False, batch_as=None
                    ),
                    SubPipeSpec(
                        the_pipe_code="generate_opposite_prompt",
                        result="prompt",
                        nb_output=None,
                        multiple_output=None,
                        batch_over=False,
                        batch_as=None,
                    ),
                    SubPipeSpec(
                        the_pipe_code="render_opposite_image",
                        result="opposite_image",
                        nb_output=None,
                        multiple_output=None,
                        batch_over=False,
                        batch_as=None,
                    ),
                ],
            ),
        ]

    async def run_compile_test() -> None:
        domain_info = _get_example_domain_information()
        concept_specs = _get_example_concept_specs_for_compile()
        pipe_specs = _get_example_pipe_specs_for_compile()

        log.info(f"Testing with {len(concept_specs)} concept specs and {len(pipe_specs)} pipe specs")

        # Create Stuff objects using StuffFactory
        domain_info_stuff = StuffFactory.make_stuff(
            concept=get_concept_provider().get_required_concept(concept_string="builder.DomainInformation"),
            content=domain_info,
            name="domain_information",
        )

        concept_specs_stuff = StuffFactory.make_stuff(
            concept=get_concept_provider().get_required_concept(concept_string="concept.ConceptSpec"),
            content=ListContent(items=concept_specs),
            name="concept_specs",
        )

        pipe_specs_stuff = StuffFactory.make_stuff(
            concept=get_concept_provider().get_required_concept(concept_string="pipe.PipeSpec"),
            content=ListContent(items=pipe_specs),
            name="pipe_specs",
        )

        # Create WorkingMemory using WorkingMemoryFactory
        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=[domain_info_stuff, concept_specs_stuff, pipe_specs_stuff])

        # Import the function directly and call it
        from pipelex.libraries.pipelines.builder.builder import compile_in_pipelex_bundle_spec

        result = await compile_in_pipelex_bundle_spec(working_memory=working_memory)

        log.info("Successfully compiled PipelexBundleSpec")
        pretty_print(result, title="Compile Result")

        # The result is directly a PipelexBundleSpec
        bundle_spec = result
        log.info(f"Bundle domain: {bundle_spec.domain}")
        log.info(f"Bundle concepts: {list(bundle_spec.concept.keys()) if bundle_spec.concept else []}")
        log.info(f"Bundle pipes: {list(bundle_spec.pipe.keys()) if bundle_spec.pipe else []}")

    asyncio.run(run_compile_test())

    # Display cost report
    get_report_delegate().generate_report()
    log.info("compile_in_pipelex_bundle_spec test completed successfully!")


@builder_debug_app.command("test-validation")
# Example usage: pipelex builder-debug test-validation
def test_validation_cmd() -> None:
    """Test the validate_pipelex_bundle_blueprint pipe with a real PipelexBundleBlueprint instance."""
    Pipelex.make(relative_config_folder_path="../../../pipelex/libraries", from_file=True)

    log.info("Creating a real PipelexBundleBlueprint instance for testing...")

    def _create_real_bundle_blueprint():
        """Create a comprehensive PipelexBundleBlueprint instance for testing."""

        # Create concept blueprints
        task_concept = ConceptSpec(
            the_concept_code="TaskDescription",
            definition="A task description with metadata",
            structure={
                "title": ConceptStructureSpec(
                    the_field_name="title", definition="The task title", type=ConceptStructureSpecFieldType.TEXT, required=True
                ),
                "description": ConceptStructureSpec(
                    the_field_name="description",
                    definition="Detailed task description",
                    type=ConceptStructureSpecFieldType.TEXT,
                    required=True,
                ),
                "estimated_hours": ConceptStructureSpec(
                    the_field_name="estimated_hours",
                    definition="Estimated hours to complete the task",
                    type=ConceptStructureSpecFieldType.NUMBER,
                    required=False,
                    default_value=1.0,
                ),
            },
        )
        analyzed_task_concept = ConceptSpec(
            the_concept_code="AnalyzedTask",
            definition="The result of task analysis",
            structure={
                "task_id": ConceptStructureSpec(
                    the_field_name="task_id", definition="Unique task identifier", type=ConceptStructureSpecFieldType.TEXT, required=True
                ),
            },
        )

        task_result_concept = ConceptSpec(
            the_concept_code="TaskResult",
            definition="The result of task processing",
            structure={
                "task_id": ConceptStructureSpec(
                    the_field_name="task_id", definition="Unique task identifier", type=ConceptStructureSpecFieldType.TEXT, required=True
                ),
                "completion_notes": ConceptStructureSpec(
                    the_field_name="completion_notes",
                    definition="Notes about task completion",
                    type=ConceptStructureSpecFieldType.TEXT,
                    required=False,
                ),
            },
        )

        user_profile_concept = ConceptSpec(
            the_concept_code="UserProfile",
            definition="User profile information",
            refines="Text",  # Refining a native concept
        )

        # Create pipe blueprints
        analyze_task_pipe = PipeLLMSpec(
            the_pipe_code="analyze_task",
            type="PipeLLM",
            definition="Analyze a task and extract key information",
            inputs={"task_description": "Text"},
            output="AnalyzedTask",
            prompt_template="Analyze this task description and extract structured information:\n\n@task_description",
            llm="llm_to_engineer",
        )

        process_user_request_pipe = PipeSequenceSpec(
            the_pipe_code="process_user_request",
            type="PipeSequence",
            definition="Process a user request by analyzing task and generating result",
            inputs={"task_description": "Text", "user_profile": "UserProfile"},
            output="AnalyzedTask",
            steps=[
                SubPipeSpec(the_pipe_code="analyze_task", result="analyzed_task"),
                SubPipeSpec(the_pipe_code="generate_task_result", result="task_result"),
            ],
        )

        generate_task_result_pipe = PipeLLMSpec(
            the_pipe_code="generate_task_result",
            type="PipeLLM",
            definition="Generate task result based on analyzed task",
            inputs={"user_profile": "UserProfile"},
            output="TaskResult",
            prompt_template="Generate a task result based on the analyzed task:\n\n@analyzed_task\n\nUser Profile:\n@user_profile",
            llm="llm_to_engineer",
        )

        validate_task_pipe = PipeConditionSpec(
            the_pipe_code="validate_task_completion",
            type="PipeCondition",
            definition="Validate task completion based on status",
            inputs={"task_result": "TaskResult"},
            output="task_management.TaskResult",
            expression="task_result.status",
            pipe_map=PipeConditionPipeMapSpec(root={"completed": "return_success", "failed": "return_failure"}),
        )

        return_success_pipe = PipeLLMSpec(
            the_pipe_code="return_success",
            type="PipeLLM",
            definition="Return success message",
            inputs={"task_result": "TaskResult"},
            output="TaskResult",
            prompt_template="Task completed successfully: @task_result",
            llm="llm_to_engineer",
        )

        return_failure_pipe = PipeLLMSpec(
            type="PipeLLM",
            the_pipe_code="return_failure",
            definition="Return failure message",
            inputs={"task_result": "TaskResult"},
            output="TaskResult",
            prompt_template="Task failed: @task_result",
            llm="llm_to_engineer",
        )

        bundle_blueprint = PipelexBundleSpec(
            domain="task_management",
            definition="A comprehensive task management pipeline for analyzing, processing, and validating tasks",
            system_prompt="You are an expert task management assistant. Analyze tasks carefully and provide structured, actionable information.",
            concept={
                "Task": task_concept,
                "TaskResult": task_result_concept,
                "user_profile": user_profile_concept,
                "AnalyzedTask": analyzed_task_concept,
            },
            pipe={
                "analyze_task": analyze_task_pipe,
                "process_user_request": process_user_request_pipe,
                "generate_task_result": generate_task_result_pipe,
                "validate_task_completion": validate_task_pipe,
                "return_success": return_success_pipe,
                "return_failure": return_failure_pipe,
            },
        )

        return bundle_blueprint

    async def run_validation_test() -> None:
        pipe_output = await execute_pipeline(
            pipe_code="validate_pipelex_bundle_blueprint",
            input_memory={
                "pipelex_bundle_blueprint": _create_real_bundle_blueprint(),
            },
        )
        pretty_print(pipe_output, title="Pipe Output")

        blueprint = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_blueprint", content_type=PipelexBundleSpec)
        pretty_print(blueprint, title="Pipelex Bundle Blueprint")

        plx_content = PipelexInterpreter.make_plx_content(blueprint=blueprint.to_blueprint())
        pretty_print(plx_content, title="PLX Content")

        with open(".built.plx", "w") as f:
            f.write(plx_content)

    asyncio.run(run_validation_test())

    # Display cost report
    get_report_delegate().generate_report()
    log.info("Validation test completed successfully!")
