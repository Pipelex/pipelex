from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from pipelex.builder.builder_errors import (
    PipeBuilderError,
    PipelexBundleUnexpectedError,
)
from pipelex.builder.bundle_header_spec import BundleHeaderSpec
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.pipe_spec_map import pipe_type_to_spec_class
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.exceptions import StuffContentTypeError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.system.registries.func_registry import pipe_func
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.core.stuffs.list_content import ListContent
    from pipelex.core.stuffs.stuff_content import StuffContent


# # TODO: Put this in a factory. Investigate why it is necessary.
def _convert_pipe_spec(pipe_spec: PipeSpecUnion) -> PipeSpecUnion:
    pipe_class = pipe_type_to_spec_class.get(pipe_spec.type)
    if pipe_class is None:
        msg = f"Unknown pipe type: {pipe_spec.type}"
        raise PipeBuilderError(msg)
    if not issubclass(pipe_class, PipeSpec):
        msg = f"Pipe class {pipe_class} is not a subclass of PipeSpec"
        raise PipeBuilderError(msg)
    return cast("PipeSpecUnion", pipe_class.model_validate(pipe_spec.model_dump(serialize_as_any=True)))

def reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec: PipelexBundleSpec, fixed_pipes: list[PipeSpecUnion]) -> PipelexBundleSpec:
    if not pipelex_bundle_spec.pipe:
        msg = "No pipes section found in bundle spec"
        raise PipelexBundleUnexpectedError(msg)

    for fixed_pipe_blueprint in fixed_pipes:
        pipe_code = fixed_pipe_blueprint.pipe_code
        pipelex_bundle_spec.pipe[pipe_code] = fixed_pipe_blueprint

    return pipelex_bundle_spec
