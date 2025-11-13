from pydantic import BaseModel

from pipelex.base_exceptions import PipelexException
from pipelex.core.bundles.exceptions import PipelexBundleError
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.exceptions import (
    ConceptDefinitionErrorData,
)
from pipelex.core.exceptions import PipelexInterpreterError
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.hub import get_library_manager, set_current_library_id
from pipelex.libraries.exceptions import (
    ConceptLoadingError,
    PipeDefinitionErrorData,
    PipeLoadingError,
)
from pipelex.pipe_run.dry_run import DryRunOutput, dry_run_pipes


class ValidateBundleError(PipelexException):
    pass


class ValidateBundleResult(BaseModel):
    blueprints: list[PipelexBundleBlueprint]
    pipes: list[PipeAbstract]
    dry_run_result: dict[str, DryRunOutput]


async def validate_bundle(
    plx_content: str | None = None, blueprints: list[PipelexBundleBlueprint] | None = None, plx_file_path: str | None = None
) -> ValidateBundleResult:
    provided_params = sum([blueprints is not None, plx_content is not None, plx_file_path is not None])
    if provided_params == 0:
        msg = "At least one of blueprints, plx_content, or plx_file_path must be provided to validate_bundle"
        raise ValidateBundleError(message=msg)
    if provided_params > 1:
        msg = "Only one of blueprints, plx_content, or plx_file_path can be provided to validate_bundle, not multiple"
        raise ValidateBundleError(message=msg)

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library_id(library_id=library_id)

    loaded_pipes: list[PipeAbstract] | None = None
    loaded_blueprints: list[PipelexBundleBlueprint] | None = None
    try:
        if blueprints is not None:
            loaded_blueprints = blueprints
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)

        if plx_content is not None:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(plx_content=plx_content)
            loaded_blueprints = [blueprint]
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])

        if plx_file_path is not None:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=plx_file_path)
            loaded_blueprints = [blueprint]
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])

        if loaded_pipes is None:
            msg = "No pipes found in the bundle"
            raise ValidateBundleError(message=msg)

        if loaded_blueprints is None:
            msg = "No blueprints found in the bundle"
            raise ValidateBundleError(message=msg)

        for pipe in loaded_pipes:
            pipe.validate_with_libraries()
        dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)

    except PipelexInterpreterError as interpreter_error:
        # TODO: enrich
        raise ValidateBundleError(message=interpreter_error.message) from interpreter_error

    except ConceptLoadingError as concept_loading_error:
        concept_def_error = concept_loading_error.concept_definition_error
        concept_definition_error_data = ConceptDefinitionErrorData(
            message=str(concept_def_error),
            domain_code=concept_def_error.domain_code,
            concept_code=concept_def_error.concept_code,
            description=concept_def_error.description,
            structure_class_python_code=concept_def_error.structure_class_python_code,
            structure_class_syntax_error_data=concept_def_error.structure_class_syntax_error_data,
            source=concept_def_error.source,
        )
        raise PipelexBundleError(
            message=concept_loading_error.message, concept_definition_errors=[concept_definition_error_data]
        ) from concept_loading_error
    except PipeLoadingError as pipe_loading_error:
        pipe_def_error = pipe_loading_error.pipe_definition_error
        pipe_definition_error_data = PipeDefinitionErrorData(
            message=str(pipe_def_error),
            domain_code=pipe_def_error.domain_code,
            pipe_code=pipe_def_error.pipe_code,
            description=pipe_def_error.description,
            source=pipe_def_error.source,
        )
        raise PipelexBundleError(message=pipe_loading_error.message, pipe_definition_errors=[pipe_definition_error_data]) from pipe_loading_error
    finally:
        library_manager.teardown()

    return ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)
