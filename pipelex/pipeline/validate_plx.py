from pydantic import ValidationError

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.exceptions import PipelexConfigurationError
from pipelex.core.interpreter import PipelexInterpreter, PLXDecodeError
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.exceptions import (
    ConceptLoadingError,
    DomainLoadingError,
    DryRunError,
    PipeLibraryError,
    PipeLoadingError,
)
from pipelex.hub import get_library_manager
from pipelex.pipe_run.dry_run import dry_run_pipes


async def validate_plx(plx_content: str, remove_after_validation: bool = True) -> tuple[PipelexBundleBlueprint, list[PipeAbstract]]:
    """Validate PLX content.

    This function:
    1. Parses PLX content into a bundle blueprint
    2. Loads pipes from the blueprint
    3. Runs static validation and dry runs all pipes

    Args:
        plx_content: The PLX content to validate
        remove_after_validation: Whether to remove the blueprint from the library manager after validation

    Returns:
        Tuple of (blueprint, pipes): The blueprint and the loaded pipes

    Raises:
        PipelexConfigurationError: For interpreter configuration errors
        PLXDecodeError: For PLX parsing/decoding errors
        ValidationError: For Pydantic validation errors in blueprint
        DomainLoadingError: For domain loading errors
        ConceptLoadingError: For concept loading errors
        PipeLoadingError: For pipe loading errors
        PipeLibraryError: For pipe library validation errors
        DryRunError: For dry run validation errors
    """
    library_manager = get_library_manager()
    blueprint: PipelexBundleBlueprint | None = None

    try:
        converter = PipelexInterpreter(file_content=plx_content)
        blueprint = converter.make_pipelex_bundle_blueprint()

        pipes = library_manager.load_from_blueprint(blueprint=blueprint)

        for pipe in pipes:
            pipe.validate_with_libraries()
            await dry_run_pipes(pipes=[pipe], raise_on_failure=True)

        if remove_after_validation:
            library_manager.remove_from_blueprint(blueprint=blueprint)
        return blueprint, pipes
    except (
        PipelexConfigurationError,
        PLXDecodeError,
        ValidationError,
        DomainLoadingError,
        ConceptLoadingError,
        PipeLoadingError,
        PipeLibraryError,
        DryRunError,
    ):
        if blueprint is not None:
            try:
                library_manager.remove_from_blueprint(blueprint=blueprint)
            except Exception as cleanup_error:
                log.error(f"Error during cleanup after validation failure: {cleanup_error}")

        raise
