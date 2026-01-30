import json
from typing import TYPE_CHECKING, Any, cast

from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.hub import get_required_pipe

if TYPE_CHECKING:
    from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
    from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence


def _collect_possible_outputs(the_pipe: PipeAbstract) -> list[dict[str, Any]]:
    """Collect all possible outputs for a pipe with native.Anything output.

    For PipeCondition, collects outputs from all mapped pipes.
    For PipeSequence, looks at the last step to determine possible outputs.

    Args:
        the_pipe: The pipe to analyze

    Returns:
        A list of possible output dicts, each containing 'concept_ref' and 'content'
    """
    pipe_type = PipeType(the_pipe.type)

    # Check if the pipe is a PipeCondition
    match pipe_type:
        case PipeType.PIPE_CONDITION:
            the_pipe = cast("PipeCondition", the_pipe)
            mapped_pipe_codes = the_pipe.pipe_dependencies()

            if not mapped_pipe_codes:
                return []

            possible_outputs: list[dict[str, Any]] = []
            for mapped_pipe_code in mapped_pipe_codes:
                mapped_pipe = get_required_pipe(pipe_code=mapped_pipe_code)
                try:
                    output_dict = mapped_pipe.output.render_stuff_spec(ConceptRepresentationFormat.JSON)
                    content = output_dict.get("content", output_dict)
                    possible_outputs.append(
                        {
                            "concept_ref": mapped_pipe.output.concept.concept_ref,
                            "content": content,
                        }
                    )
                except Exception:
                    # If we can't render this pipe's output, add a placeholder
                    possible_outputs.append(
                        {
                            "concept_ref": mapped_pipe.output.concept.concept_ref,
                            "content": "<unable to render>",
                        }
                    )

            return possible_outputs

        case PipeType.PIPE_SEQUENCE:
            the_pipe = cast("PipeSequence", the_pipe)
            sequential_sub_pipes: list[Any] = getattr(the_pipe, "sequential_sub_pipes", [])
            if not sequential_sub_pipes:
                return []

            last_sub_pipe = sequential_sub_pipes[-1]
            last_pipe_code: str = getattr(last_sub_pipe, "pipe_code", "")
            if not last_pipe_code:
                return []

            last_pipe = get_required_pipe(pipe_code=last_pipe_code)

            # If last pipe also has Anything output, recurse
            if last_pipe.output.concept.code == NativeConceptCode.ANYTHING:
                return _collect_possible_outputs(last_pipe)

            # Otherwise render the last pipe's output
            try:
                output_dict = last_pipe.output.render_stuff_spec(ConceptRepresentationFormat.JSON)
                content = output_dict.get("content", output_dict)
                return [
                    {
                        "concept_ref": last_pipe.output.concept.concept_ref,
                        "content": content,
                    }
                ]
            except Exception:
                return []

        case (
            PipeType.PIPE_FUNC
            | PipeType.PIPE_IMG_GEN
            | PipeType.PIPE_COMPOSE
            | PipeType.PIPE_LLM
            | PipeType.PIPE_EXTRACT
            | PipeType.PIPE_BATCH
            | PipeType.PIPE_PARALLEL
        ):
            return []


def render_output(the_pipe: PipeAbstract, indent: int = 2) -> str:
    """Render a JSON representation of the pipe's output.

    For pipes with native.Anything output, shows all possible outputs from mapped pipes
    with keys "output_option_1", "output_option_2", etc.

    Args:
        the_pipe: The pipe to render output for
        indent: Number of spaces for indentation (default: 2)

    Returns:
        Formatted JSON string with the output representation

    Raises:
        ValueError: If the output cannot be rendered
    """
    # Check if output is native.Anything (has no specific shape)
    if the_pipe.output.concept.code == NativeConceptCode.ANYTHING:
        possible_outputs = _collect_possible_outputs(the_pipe)

        if not possible_outputs:
            msg = f"Output is '{NativeConceptCode.ANYTHING.concept_ref}' which has no specific shape and no possible outputs could be determined."
            raise ValueError(msg)

        # Build dict with "output_option_1", "output_option_2", etc.
        # Each option includes "concept" and "content" fields
        result: dict[str, Any] = {}
        for idx, output_info in enumerate(possible_outputs, start=1):
            result[f"output_option_{idx}"] = {
                "concept": output_info["concept_ref"],
                "content": output_info["content"],
            }

        return json.dumps(result, indent=indent, ensure_ascii=False)

    # Normal output rendering - returns dict with "concept" and "content"
    output_dict = the_pipe.output.render_stuff_spec(ConceptRepresentationFormat.JSON)
    return json.dumps(output_dict, indent=indent, ensure_ascii=False)
