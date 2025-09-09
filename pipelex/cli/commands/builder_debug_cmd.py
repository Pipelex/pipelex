"""CLI commands for debugging and running intermediate steps of the builder pipeline."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from pipelex import log, pretty_print
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
    from pipelex.core.pipes.pipe_blueprint import AllowedPipeTypes

    concept_specs = _get_example_concept_specs()

    # Create concept spec lookup
    concept_lookup = {spec.the_concept_code: spec for spec in concept_specs}

    return [
        PipeSignature(
            code="analyze_task",
            type=AllowedPipeTypes.PIPE_LLM,
            definition="Analyze a task description and extract key information",
            inputs={"task_description": concept_lookup["TaskDescription"]},
            output=concept_lookup["TaskResult"],
        ),
        PipeSignature(
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
        concept_spec_blueprints = []

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

            concept_blueprints_list = ListContent(items=[stuff.content for stuff in concept_spec_blueprints])

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
        concept_spec_blueprints = []

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
        pipe_spec_blueprints = []

        # Create list content for concept spec blueprints
        from pipelex.core.stuffs.stuff_content import ListContent

        concept_blueprints_list = ListContent(items=[stuff.content for stuff in concept_spec_blueprints])

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
