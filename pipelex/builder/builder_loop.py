from rich.console import Console

from pipelex import log, pretty_print
from pipelex.builder.builder import (
    PipelexBundleSpec,
    PipeSpecUnion,
    reconstruct_bundle_with_pipe_fixes,
)
from pipelex.builder.builder_errors import (
    PipeBuilderError,
    PipelexBundleError,
    PipelexBundleNoFixForError,
    PipelexBundleUnexpectedError,
)
from pipelex.builder.builder_validation import fix_inputs_consistency, validate_bundle_spec
from pipelex.client.protocol import PipelineInputs
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories
from pipelex.exceptions import PipelineExecutionError, StaticValidationErrorType, WorkingMemoryStuffNotFoundError
from pipelex.hub import get_required_pipe
from pipelex.language.plx_factory import PlxFactory
from pipelex.pipeline.execute import execute_pipeline
from pipelex.tools.misc.file_utils import get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path


class BuilderLoop:
    async def build_and_fix(
        self,
        pipe_code: str,
        inputs: PipelineInputs | None = None,
        is_save_first_iteration_enabled: bool = True,
        is_save_second_iteration_enabled: bool = True,
        is_save_working_memory_enabled: bool = True,
    ) -> PipelexBundleSpec:
        pretty_print(f"Building and fixing with {pipe_code}")
        try:
            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                inputs=inputs,
            )
        except PipelineExecutionError as exc:
            msg = f"Builder loop: Failed to execute pipeline: {exc}."
            console = Console(stderr=True)
            console.print_exception()
            raise PipeBuilderError(message=msg) from exc
        pretty_print(pipe_output, title="Pipe Output")

        if is_save_working_memory_enabled:
            working_memory_path = get_incremental_file_path(
                base_path="results",
                base_name="working_memory",
                extension="json",
            )
            save_as_json_to_path(object_to_save=pipe_output.working_memory.smart_dump(), path=working_memory_path)

        try:
            pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
        except WorkingMemoryStuffNotFoundError as exc:
            msg = f"Builder loop: Failed to get pipelex bundle spec: {exc}."
            raise PipeBuilderError(message=msg, working_memory=pipe_output.working_memory) from exc
        pretty_print(pipelex_bundle_spec, title="Pipelex Bundle Spec • 1st iteration")
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())

        if is_save_first_iteration_enabled:
            first_iteration_path = get_incremental_file_path(
                base_path="results",
                base_name="generated_pipeline_1st_iteration",
                extension="plx",
            )
            save_text_to_path(text=plx_content, path=first_iteration_path)

        # Fix input consistency for all PipeController pipes before validation
        log.dev("🔄 Calling fix_inputs_consistency() to ensure PipeController inputs are consistent")
        try:
            pipelex_bundle_spec = fix_inputs_consistency(bundle_spec=pipelex_bundle_spec)
        except PipelexBundleError as bundle_error:
            # Let the error fall through to the existing error handling
            pretty_print(bundle_error.as_structured_content(), title="Pipelex Bundle Error (during input fix)")
            pipelex_bundle_spec = self._fix_bundle_error(
                bundle_error=bundle_error,
                pipelex_bundle_spec=pipelex_bundle_spec,
                is_save_second_iteration_enabled=is_save_second_iteration_enabled,
            )

        # Save the fixed bundle for debugging if enabled
        if is_save_first_iteration_enabled:
            plx_content_after_fix = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
            first_iteration_after_fix_path = get_incremental_file_path(
                base_path="results",
                base_name="generated_pipeline_1st_iteration_after_fix",
                extension="plx",
            )
            save_text_to_path(text=plx_content_after_fix, path=first_iteration_after_fix_path)

        try:
            await validate_bundle_spec(bundle_spec=pipelex_bundle_spec)
        except PipelexBundleError as bundle_error:
            pretty_print(bundle_error.as_structured_content(), title="Pipelex Bundle Error")
            pipelex_bundle_spec = self._fix_bundle_error(
                bundle_error=bundle_error,
                pipelex_bundle_spec=pipelex_bundle_spec,
                is_save_second_iteration_enabled=is_save_second_iteration_enabled,
            )

        return pipelex_bundle_spec

    def _fix_bundle_error(
        self,
        bundle_error: PipelexBundleError,
        pipelex_bundle_spec: PipelexBundleSpec,
        is_save_second_iteration_enabled: bool,
    ) -> PipelexBundleSpec:
        fixed_pipes: list[PipeSpecUnion] = []

        # Fix static validation errors for PipeController inputs
        if bundle_error.static_validation_error:
            static_error = bundle_error.static_validation_error
            if not static_error.pipe_code:
                msg = "Static validation error had no pipe code"
                raise PipelexBundleUnexpectedError(message=msg) from bundle_error
            if not pipelex_bundle_spec.pipe:
                msg = "Static validation error pipelex_bundle_spec had no pipe section"
                raise PipelexBundleUnexpectedError(message=msg) from bundle_error
            pipe_spec = pipelex_bundle_spec.pipe.get(static_error.pipe_code)
            if not pipe_spec:
                msg = f"Static validation error pipelex_bundle_spec had no pipe spec for considered pipe code: '{static_error.pipe_code}'"
                raise PipelexBundleUnexpectedError(message=msg) from bundle_error
            match static_error.error_type:
                case StaticValidationErrorType.MISSING_INPUT_VARIABLE | StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE:
                    if not AllowedPipeCategories.is_controller_by_str(category_str=pipe_spec.pipe_category):
                        msg = (
                            f"Static validation error: pipelex_bundle_spec had an input requirement error for a pipe spec of type "
                            f"{pipe_spec.type} for considered pipe code: '{static_error.pipe_code}' but it was not a PipeController. "
                            "We don't support fixing this error yet. Dump of the pipelex_bundle_spec:\n\n"
                            f"{pipelex_bundle_spec.model_dump_json(serialize_as_any=True, indent=2)}"
                        )
                        raise PipelexBundleNoFixForError(message=msg) from bundle_error

                    pipe = get_required_pipe(pipe_code=static_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()
                    # Build the new inputs dict from needed_inputs
                    new_inputs: dict[str, str] = {}
                    for named_requirement in needed_inputs.named_input_requirements:
                        new_inputs[named_requirement.variable_name] = named_requirement.concept.code
                    # Update the pipe spec inputs
                    pipe_spec.inputs = new_inputs
                    fixed_pipes.append(pipe_spec)
                case StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT:
                    msg = "Static validation error had inadequate input concept. We don't support fixing this error yet."
                    raise PipelexBundleNoFixForError(message=msg) from bundle_error
                case StaticValidationErrorType.TOO_MANY_CANDIDATE_INPUTS:
                    msg = "Static validation error had too many candidate inputs. We don't support fixing this error yet."
                    raise PipelexBundleNoFixForError(message=msg) from bundle_error

        if fixed_pipes and is_save_second_iteration_enabled:
            pipelex_bundle_spec = reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec=pipelex_bundle_spec, fixed_pipes=fixed_pipes)
            pretty_print(pipelex_bundle_spec, title="Pipelex Bundle Spec • 2nd iteration")
            plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
            second_iteration_path = get_incremental_file_path(
                base_path="results",
                base_name="generated_pipeline_2nd_iteration",
                extension="plx",
            )
            save_text_to_path(text=plx_content, path=second_iteration_path)

        return pipelex_bundle_spec
