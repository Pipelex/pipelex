"""CLI commands for debugging and running intermediate steps of the builder pipeline."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer

from pipelex import log, pretty_print
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes
from pipelex.hub import get_report_delegate
from pipelex.libraries.pipelines.builder.concept.concept import ConceptSpec
from pipelex.libraries.pipelines.builder.pipe.pipe import PipeSignature
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline

builder_debug_app = typer.Typer(help="Debug and test intermediate steps of the builder pipeline", no_args_is_help=True)


def _get_example_concept_specs() -> list[ConceptSpec]:
    """Get hardcoded example concept specs for testing."""
    return [
        ConceptSpec(
            the_concept_code="TaskDescription",
            description="A description of a task that needs to be completed",
            structure="{ 'title': 'str', 'description': 'str', 'priority': 'str', 'due_date': 'Optional[datetime]' }",
        ),
        ConceptSpec(
            the_concept_code="TaskResult",
            description="The result of completing a task",
            structure="{ 'task_id': 'str', 'status': 'str', 'completion_notes': 'str', 'completed_at': 'datetime' }",
        ),
        ConceptSpec(
            the_concept_code="UserProfile",
            description="A user profile containing personal information",
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
def build_concepts_cmd(
    relative_config_folder_path: Annotated[
        str,
        typer.Option(
            "--config-folder-path",
            "-c",
            help="Relative path to the config folder path (libraries)",
        ),
    ] = "./pipelex_libraries",
) -> None:
    """Run the build_concept_blueprint step with hardcoded example data."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

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
def create_pipes_cmd(
    relative_config_folder_path: Annotated[
        str,
        typer.Option(
            "--config-folder-path",
            "-c",
            help="Relative path to the config folder path (libraries)",
        ),
    ] = "./pipelex_libraries",
) -> None:
    """Run the create_pipes_from_signatures step with hardcoded example data."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

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
            from pipelex.core.stuffs.stuff_content import ListContent

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
def full_pipeline_cmd(
    relative_config_folder_path: Annotated[
        str,
        typer.Option(
            "--config-folder-path",
            "-c",
            help="Relative path to the config folder path (libraries)",
        ),
    ] = "./pipelex_libraries",
) -> None:
    """Run both build_concept_blueprint and create_pipes_from_signatures steps in sequence."""
    Pipelex.make(relative_config_folder_path=relative_config_folder_path, from_file=False)

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
        from pipelex.core.stuffs.stuff_content import ListContent

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
    Pipelex.make(relative_config_folder_path="pipelex/libraries", from_file=False)

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


@builder_debug_app.command("test-validation")
# Example usage: pipelex builder-debug test-validation
def test_validation_cmd(
    relative_config_folder_path: Annotated[
        str,
        typer.Option(
            "--config-folder-path",
            "-c",
            help="Relative path to the config folder path (libraries)",
        ),
    ] = "./pipelex_libraries",
) -> None:
    """Test the validate_pipelex_bundle_blueprint pipe with a real PipelexBundleBlueprint instance."""
    Pipelex.make(relative_config_folder_path="pipelex/libraries", from_file=False)

    log.info("Creating a real PipelexBundleBlueprint instance for testing...")

    def _create_real_bundle_blueprint():
        """Create a comprehensive PipelexBundleBlueprint instance for testing."""
        from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprint
        from pipelex.libraries.pipelines.builder.concept.concept import (
            ConceptBlueprint,
            ConceptStructureBlueprint,
            ConceptStructureBlueprintFieldType,
        )
        from pipelex.libraries.pipelines.builder.pipe.pipe_condition import PipeConditionBlueprint, PipeConditionPipeMapBlueprint
        from pipelex.libraries.pipelines.builder.pipe.pipe_llm import PipeLLMBlueprint
        from pipelex.libraries.pipelines.builder.pipe.pipe_sequence import PipeSequenceBlueprint
        from pipelex.libraries.pipelines.builder.pipe.sub_pipe import SubPipeBlueprint

        # Create concept blueprints
        task_concept = ConceptBlueprint(
            definition="A task description with metadata",
            structure={
                "title": ConceptStructureBlueprint(definition="The task title", type=ConceptStructureBlueprintFieldType.TEXT, required=True),
                "description": ConceptStructureBlueprint(
                    definition="Detailed task description", type=ConceptStructureBlueprintFieldType.TEXT, required=True
                ),
                # "priority": ConceptStructureBlueprint(definition="Task priority level", choices=["low", "medium", "high", "urgent"], required=True),
                "estimated_hours": ConceptStructureBlueprint(
                    definition="Estimated hours to complete the task",
                    type=ConceptStructureBlueprintFieldType.NUMBER,
                    required=False,
                    default_value=1.0,
                ),
                # "tags": ConceptStructureBlueprint(
                #     definition="List of task tags", type=ConceptStructureBlueprintFieldType.LIST, item_type="text", required=False, default_value=[]
                # ),
            },
        )
        analyzed_task_concept = ConceptBlueprint(
            definition="The result of task analysis",
            structure={
                "task_id": ConceptStructureBlueprint(
                    definition="Unique task identifier", type=ConceptStructureBlueprintFieldType.TEXT, required=True
                ),
                # "status": ConceptStructureBlueprint(
                #     definition="Task completion status", choices=["pending", "in_progress", "completed", "failed"], required=True
                # ),
            },
        )

        task_result_concept = ConceptBlueprint(
            definition="The result of task processing",
            structure={
                "task_id": ConceptStructureBlueprint(
                    definition="Unique task identifier", type=ConceptStructureBlueprintFieldType.TEXT, required=True
                ),
                # "status": ConceptStructureBlueprint(
                #     definition="Task completion status", choices=["pending", "in_progress", "completed", "failed"], required=True
                # ),
                "completion_notes": ConceptStructureBlueprint(
                    definition="Notes about task completion", type=ConceptStructureBlueprintFieldType.TEXT, required=False
                ),
                # "metadata": ConceptStructureBlueprint(
                #     definition="Additional task metadata",
                #     type=ConceptStructureBlueprintFieldType.DICT,
                #     key_type="text",
                #     value_type="text",
                #     required=False,
                #     default_value={},
                # ),
            },
        )

        user_profile_concept = ConceptBlueprint(
            definition="User profile information",
            refines="Text",  # Refining a native concept
        )

        # Create pipe blueprints
        analyze_task_pipe = PipeLLMBlueprint(
            type="PipeLLM",
            definition="Analyze a task and extract key information",
            inputs={"task_description": "Text"},
            output="AnalyzedTask",
            prompt_template="Analyze this task description and extract structured information:\n\n@task_description",
            llm="llm_to_engineer",
        )

        process_user_request_pipe = PipeSequenceBlueprint(
            type="PipeSequence",
            definition="Process a user request by analyzing task and generating result",
            inputs={"task_description": "Text", "user_profile": "UserProfile"},
            output="AnalyzedTask",
            steps=[
                SubPipeBlueprint(pipe="analyze_task", result="analyzed_task"),
                SubPipeBlueprint(pipe="generate_task_result", result="task_result"),
            ],
        )

        generate_task_result_pipe = PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate task result based on analyzed task",
            inputs={"user_profile": "UserProfile"},
            output="TaskResult",
            prompt_template="Generate a task result based on the analyzed task:\n\n@analyzed_task\n\nUser Profile:\n@user_profile",
            llm="llm_to_engineer",
        )

        validate_task_pipe = PipeConditionBlueprint(
            type="PipeCondition",
            definition="Validate task completion based on status",
            inputs={"task_result": "TaskResult"},
            output="task_management.TaskResult",
            expression="task_result.status",
            pipe_map=PipeConditionPipeMapBlueprint(root={"completed": "return_success", "failed": "return_failure"}),
        )

        return_success_pipe = PipeLLMBlueprint(
            type="PipeLLM",
            definition="Return success message",
            inputs={"task_result": "TaskResult"},
            output="TaskResult",
            prompt_template="Task completed successfully: @task_result",
            llm="llm_to_engineer",
        )

        return_failure_pipe = PipeLLMBlueprint(
            type="PipeLLM",
            definition="Return failure message",
            inputs={"task_result": "TaskResult"},
            output="TaskResult",
            prompt_template="Task failed: @task_result",
            llm="llm_to_engineer",
        )

        # Create the complete bundle blueprint
        bundle_blueprint = PipelexBundleBlueprint(
            domain="task_management",
            definition="A comprehensive task management pipeline for analyzing, processing, and validating tasks",
            system_prompt="You are an expert task management assistant. Analyze tasks carefully and provide structured, actionable information.",
            concept={
                "Task": task_concept,
                "TaskResult": task_result_concept,
                "UserProfile": user_profile_concept,
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
        from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprint

        blueprint = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_blueprint", content_type=PipelexBundleBlueprint)
        pretty_print(blueprint, title="Pipelex Bundle Blueprint")
        from pipelex.core.interpreter import PipelexInterpreter

        plx_content = PipelexInterpreter.make_plx_content(blueprint=blueprint.to_core_blueprint())
        pretty_print(plx_content, title="PLX Content")

        with open(".built.plx", "w") as f:
            f.write(plx_content)

    asyncio.run(run_validation_test())

    # Display cost report
    get_report_delegate().generate_report()
    log.info("Validation test completed successfully!")
