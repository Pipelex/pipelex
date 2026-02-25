from pipelex.builder.builder_errors import (
    PipelexBundleUnexpectedError,
)
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion


def reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec: PipelexBundleSpec, fixed_pipes: list[PipeSpecUnion]) -> PipelexBundleSpec:
    if not pipelex_bundle_spec.pipe:
        msg = "No pipes section found in bundle spec"
        raise PipelexBundleUnexpectedError(msg)

    for fixed_pipe_blueprint in fixed_pipes:
        pipe_code = fixed_pipe_blueprint.pipe_code
        pipelex_bundle_spec.pipe[pipe_code] = fixed_pipe_blueprint

    return pipelex_bundle_spec
