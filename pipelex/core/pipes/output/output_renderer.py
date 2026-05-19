import json
from typing import TYPE_CHECKING, Any, cast

from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.hub import get_required_pipe

if TYPE_CHECKING:
    from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
    from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence


def _collect_possible_outputs(
    the_pipe: PipeAbstract,
    output_format: ConceptRepresentationFormat = ConceptRepresentationFormat.JSON,
) -> list[dict[str, Any]]:
    """Collect all possible outputs for a pipe with native.Anything output.

    For PipeCondition, collects outputs from all mapped pipes.
    For PipeSequence, looks at the last step to determine possible outputs.

    Args:
        the_pipe: The pipe to analyze
        output_format: The format to generate (JSON, PYTHON, or TYPESCRIPT)

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
                    output_dict = mapped_pipe.output.render_stuff_spec(output_format)
                    content = output_dict.get("content", output_dict)
                    possible_outputs.append(
                        {
                            "concept_ref": mapped_pipe.output.concept.concept_ref,
                            "content": content,
                        }
                    )
                except (PipelexError, ValueError):
                    # A dynamic concept whose structure cannot be rendered (unresolved structure
                    # class, unsupported shape): show a placeholder. Unexpected errors propagate.
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
                return _collect_possible_outputs(last_pipe, output_format)

            # Otherwise render the last pipe's output
            try:
                output_dict = last_pipe.output.render_stuff_spec(output_format)
                content = output_dict.get("content", output_dict)
                return [
                    {
                        "concept_ref": last_pipe.output.concept.concept_ref,
                        "content": content,
                    }
                ]
            except (PipelexError, ValueError):
                # A dynamic concept whose structure cannot be rendered (unresolved structure
                # class, unsupported shape): report no possible outputs. Unexpected errors propagate.
                return []

        case (
            PipeType.PIPE_FUNC
            | PipeType.PIPE_IMG_GEN
            | PipeType.PIPE_COMPOSE
            | PipeType.PIPE_LLM
            | PipeType.PIPE_EXTRACT
            | PipeType.PIPE_SEARCH
            | PipeType.PIPE_STRUCTURE
            | PipeType.PIPE_BATCH
            | PipeType.PIPE_PARALLEL
        ):
            return []


def render_output(
    the_pipe: PipeAbstract,
    indent: int = 2,
    output_format: ConceptRepresentationFormat = ConceptRepresentationFormat.JSON,
) -> str:
    """Render a representation of the pipe's output.

    For pipes with native.Anything output, shows all possible outputs from mapped pipes
    with keys "output_option_1", "output_option_2", etc.

    Args:
        the_pipe: The pipe to render output for
        indent: Number of spaces for indentation (default: 2, only used for JSON)
        output_format: The format to generate (JSON, PYTHON, or SCHEMA)

    Returns:
        Formatted string with the output representation:
        - JSON: JSON object with concept and content fields
        - PYTHON: Python code with class instantiation
        - SCHEMA: JSON Schema definition

    Raises:
        ValueError: If the output cannot be rendered
    """
    # Handle each format type
    match output_format:
        case ConceptRepresentationFormat.SCHEMA:
            return _render_schema_output(the_pipe, indent)
        case ConceptRepresentationFormat.PYTHON:
            return _render_python_output(the_pipe)
        case ConceptRepresentationFormat.JSON:
            return _render_json_output(the_pipe, indent)


def _render_json_output(the_pipe: PipeAbstract, indent: int = 2) -> str:
    """Render JSON representation of the pipe's output.

    Args:
        the_pipe: The pipe to render output for
        indent: Number of spaces for indentation

    Returns:
        JSON string with concept and content fields

    Raises:
        ValueError: If the output cannot be rendered
    """
    # Check if output is native.Anything (has no specific shape)
    if the_pipe.output.concept.code == NativeConceptCode.ANYTHING:
        possible_outputs = _collect_possible_outputs(the_pipe, ConceptRepresentationFormat.JSON)

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


def _render_python_output(the_pipe: PipeAbstract) -> str:
    """Render Python code representation of the pipe's output.

    Args:
        the_pipe: The pipe to render output for

    Returns:
        Python code string with class instantiation

    Raises:
        ValueError: If the output cannot be rendered
    """
    # Check if output is native.Anything (has no specific shape)
    if the_pipe.output.concept.code == NativeConceptCode.ANYTHING:
        possible_outputs = _collect_possible_outputs(the_pipe, ConceptRepresentationFormat.PYTHON)

        if not possible_outputs:
            msg = f"Output is '{NativeConceptCode.ANYTHING.concept_ref}' which has no specific shape and no possible outputs could be determined."
            raise ValueError(msg)

        # Generate Python code for multiple possible outputs
        lines: list[str] = [
            "# Multiple possible output types",
            "# The actual output will be one of the following:",
            "",
        ]

        for idx, output_info in enumerate(possible_outputs, start=1):
            concept_ref = output_info["concept_ref"]
            content = output_info["content"]
            lines.append(f"# Option {idx}: {concept_ref}")
            lines.append(f"output_{idx} = {content}")
            lines.append("")

        return "\n".join(lines)

    # Normal output rendering
    output_dict = the_pipe.output.render_stuff_spec(ConceptRepresentationFormat.PYTHON)
    concept_ref = output_dict.get("concept", "")
    content = output_dict.get("content", "")

    lines = [
        f"# Concept: {concept_ref}",
        f"output = {content}",
    ]

    return "\n".join(lines)


def _render_schema_output(the_pipe: PipeAbstract, indent: int = 2) -> str:
    """Render JSON Schema for the pipe's output.

    Args:
        the_pipe: The pipe to render output for
        indent: Number of spaces for indentation

    Returns:
        JSON Schema as a formatted string

    Raises:
        ValueError: If the output cannot be rendered
    """
    # Check if output is native.Anything (has no specific shape)
    if the_pipe.output.concept.code == NativeConceptCode.ANYTHING:
        possible_outputs = _collect_possible_outputs(the_pipe, ConceptRepresentationFormat.SCHEMA)

        if not possible_outputs:
            msg = f"Output is '{NativeConceptCode.ANYTHING.concept_ref}' which has no specific shape and no possible outputs could be determined."
            raise ValueError(msg)

        # Build dict with schema options
        result: dict[str, Any] = {}
        for idx, output_info in enumerate(possible_outputs, start=1):
            result[f"schema_option_{idx}"] = {
                "concept": output_info["concept_ref"],
                "content": output_info["content"],
            }

        return json.dumps(result, indent=indent, ensure_ascii=False)

    # Normal output rendering - get JSON Schema directly
    output_dict = the_pipe.output.render_stuff_spec(ConceptRepresentationFormat.SCHEMA)
    return json.dumps(output_dict, indent=indent, ensure_ascii=False)
