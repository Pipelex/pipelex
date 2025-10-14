"""Generate Python runner code from pipe definitions and concepts."""

from typing import Any

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.pipe_abstract import PipeAbstract


def _value_to_python_code(value: Any, indent_level: int = 0) -> str:
    """Convert a value to Python code representation recursively.

    Args:
        value: The value to convert (can be str, int, dict, list, etc.)
        indent_level: Current indentation level for nested dicts

    Returns:
        String representation of Python code
    """
    indent = "    " * indent_level

    if isinstance(value, str):
        # String value - add quotes
        return f'"{value}"'
    elif isinstance(value, bool):
        # Boolean - Python True/False
        return str(value)
    elif isinstance(value, (int, float)):
        # Numeric value
        return str(value)
    elif isinstance(value, list):
        # List - recursively convert items
        if not value:
            return "[]"
        items: list[str] = [_value_to_python_code(item, indent_level + 1) for item in value]  # pyright: ignore[reportUnknownVariableType]
        return "[" + ", ".join(items) + "]"
    elif isinstance(value, dict):
        # Dict - recursively convert with proper formatting
        if not value:
            return "{}"
        lines: list[str] = []
        for key, val in value.items():  # pyright: ignore[reportUnknownVariableType]
            val_code = _value_to_python_code(val, indent_level + 1)
            lines.append(f'{indent}    "{key}": {val_code}')
        return "{\n" + ",\n".join(lines) + f"\n{indent}}}"
    else:
        # Fallback - use repr
        return repr(value)


def generate_compact_memory_entry(var_name: str, concept: Concept) -> str:
    """Generate the compact_memory dictionary entry for a given input."""
    example_value = concept.get_compact_memory_example(var_name)

    # Convert the example value to a Python code string
    value_str = _value_to_python_code(example_value, indent_level=3)

    return f'            "{var_name}": {value_str},'


def generate_runner_code(pipe: PipeAbstract) -> str:
    """Generate the complete Python runner code for a pipe."""
    pipe_code = pipe.code
    inputs = pipe.inputs

    # Build import section - minimal imports since we use compact memory format
    import_lines = [
        "import asyncio",
        "",
        "from pipelex.pipelex import Pipelex",
        "from pipelex.pipeline.execute import execute_pipeline",
    ]

    # Build input_memory entries
    if inputs.nb_inputs > 0:
        input_memory_entries: list[str] = []
        for var_name, input_req in inputs.root.items():
            concept = input_req.concept
            entry = generate_compact_memory_entry(var_name, concept)
            input_memory_entries.append(entry)
        input_memory_block = "\n".join(input_memory_entries)
    else:
        input_memory_block = "        # No inputs required"

    # Build the main function
    function_lines = [
        "",
        "",
        f"async def run_{pipe_code}():",
        '    """Run the pipeline and return the result."""',
        "    return await execute_pipeline(",
        f'        pipe_code="{pipe_code}",',
    ]

    if inputs.nb_inputs > 0:
        function_lines.extend(
            [
                "        input_memory={",
                input_memory_block,
                "        },",
            ]
        )

    function_lines.extend(
        [
            "    )",
            "",
            "",
            'if __name__ == "__main__":',
            "    # Initialize Pipelex",
            "    Pipelex.make()",
            "",
            "    # Run the pipeline",
            f"    result = asyncio.run(run_{pipe_code}())",
            "",
        ]
    )

    # Combine everything
    code_lines = import_lines + function_lines
    return "\n".join(code_lines)
