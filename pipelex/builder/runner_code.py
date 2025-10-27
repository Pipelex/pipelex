"""Runner code generation utilities for Pipelex pipelines.

This module provides functions to generate executable Python code and JSON input examples
for Pipelex pipelines. It supports two output formats:

1. **Python Code Format**: Generates Python code with class instantiations
   Example: PDFContent(url="document.pdf")

2. **JSON Format**: Generates pure JSON with concept metadata
   Example: {"concept": "native.PDF", "content": {"url": "document.pdf"}}

Main Functions:
--------------
- generate_runner_code(pipe): Generate complete executable Python script
- generate_input_memory_block_python(inputs): Generate just the Python inputs dict
- generate_input_memory_json(inputs): Generate JSON inputs as dict
- generate_input_memory_json_string(inputs): Generate JSON inputs as formatted string

Example Usage:
-------------
```python
from pipelex.hub import get_required_pipe
from pipelex.builder.runner_code import (
    generate_runner_code,
    generate_input_memory_block_python,
    generate_input_memory_json,
    generate_input_memory_json_string,
)

# Get a pipe
pipe = get_required_pipe("my_pipe")

# Generate complete Python runner code
python_code = generate_runner_code(pipe)
print(python_code)

# Generate just the Python input memory block
python_inputs = generate_input_memory_block_python(pipe.inputs)
print(f"inputs = {python_inputs}")

# Generate JSON input memory (as dict)
json_inputs = generate_input_memory_json(pipe.inputs)
print(json_inputs)

# Generate JSON input memory (as formatted string)
json_string = generate_input_memory_json_string(pipe.inputs, indent=2)
print(json_string)
```

Python Output Example:
---------------------
```python
import asyncio

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execute import execute_pipeline


async def run_my_pipe():
    return await execute_pipeline(
        pipe_code="my_pipe",
        inputs={
            "image": ImageContent(url="image_url"),
        },
    )


if __name__ == "__main__":
    Pipelex.make()
    result = asyncio.run(run_my_pipe())
```

JSON Output Example:
-------------------
```json
{
  "image": {
    "concept": "native.Image",
    "content": {
      "url": "image_url"
    }
  }
}
```
"""

import json
from typing import Any, cast

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_abstract import PipeAbstract


def value_to_json(value: Any) -> Any:
    """Convert a value to pure JSON representation (dict/list/primitives only).

    Args:
        value: The value to convert

    Returns:
        Pure JSON-serializable representation (no Python classes)
    """
    if isinstance(value, dict) and "_class" in value:
        # Convert Content class instantiation to pure JSON
        # E.g., {"_class": "PDFContent", "url": "..."} -> {"url": "..."}
        class_name = value["_class"]  # pyright: ignore[reportUnknownVariableType]
        if class_name in {"PDFContent", "ImageContent"}:
            url = value.get("url", "your_url")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
            return {"url": cast("str", url)}
        # For other classes, remove the _class key and return the rest
        return {k: value_to_json(v) for k, v in value.items() if k != "_class"}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    elif isinstance(value, dict) and "concept_code" in value and "content" in value:
        # Convert concept_code format to concept format with pure JSON content
        concept_code = value["concept_code"]  # pyright: ignore[reportUnknownVariableType]
        content = value["content"]  # pyright: ignore[reportUnknownVariableType]

        # Recursively convert content to JSON
        content_json = value_to_json(content)

        return {"concept": cast("str", concept_code), "content": content_json}
    elif isinstance(value, str | bool | int | float):
        return value
    elif isinstance(value, list):
        return [value_to_json(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    elif isinstance(value, dict):
        return {k: value_to_json(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    else:
        # For other types, try to convert to string
        return str(value)


def value_to_python_code(value: Any, indent_level: int = 0) -> str:
    """Convert a value to Python code representation recursively.

    Args:
        value: The value to convert (can be str, int, dict, list, etc.)
        indent_level: Current indentation level for nested dicts

    Returns:
        String representation of Python code
    """
    indent = "    " * indent_level

    if isinstance(value, dict) and "_class" in value:
        # Special handling for Content class instantiation (e.g., PDFContent, ImageContent)
        class_name = value["_class"]  # pyright: ignore[reportUnknownVariableType]
        if class_name in {"PDFContent", "ImageContent"}:
            url = value.get("url", "your_url")  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
            return f'{class_name}(url="{url}")'
        return str(value)  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(value, dict) and "concept_code" in value and "content" in value:
        # Special handling for refined concepts with explicit concept_code
        # Format: {"concept": "domain.ConceptCode", "content": ContentClass(...)}
        concept_code = value["concept_code"]  # pyright: ignore[reportUnknownVariableType]
        content = value["content"]  # pyright: ignore[reportUnknownVariableType]

        # Generate the content part
        content_code = value_to_python_code(content, indent_level + 1)

        # Return the full format with concept and content
        return f'{{\n{indent}    "concept": "{concept_code}",\n{indent}    "content": {content_code},\n{indent}}}'
    elif isinstance(value, str):
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
        items: list[str] = [value_to_python_code(item, indent_level + 1) for item in value]  # pyright: ignore[reportUnknownVariableType]
        return "[" + ", ".join(items) + "]"
    elif isinstance(value, dict):
        # Dict - recursively convert with proper formatting
        if not value:
            return "{}"
        lines_dict: list[str] = []
        for key, val in value.items():  # pyright: ignore[reportUnknownVariableType]
            val_code = value_to_python_code(val, indent_level + 1)
            lines_dict.append(f'{indent}    "{key}": {val_code}')
        return "{\n" + ",\n".join(lines_dict) + f"\n{indent}}}"
    else:
        # Fallback - use repr
        return repr(value)


def generate_compact_memory_entry(var_name: str, concept: Concept) -> str:
    """Generate the pipeline_inputs dictionary entry for a given input (Python code version)."""
    example_value = concept.get_compact_memory_example(var_name)

    # Convert the example value to a Python code string
    value_str = value_to_python_code(example_value, indent_level=3)

    return f'            "{var_name}": {value_str},'


def generate_json_memory_entry(var_name: str, concept: Concept) -> dict[str, Any]:
    """Generate the pipeline_inputs dictionary entry for a given input (pure JSON version).

    Returns:
        A tuple of (var_name, json_value) where json_value is pure JSON (dict/list/primitives)
    """
    example_value = concept.get_compact_memory_example(var_name)

    # Convert to JSON - always wrap with concept if not already present
    json_value = value_to_json(example_value)

    # For simple values (strings for Text, numbers for Number), wrap with concept
    if isinstance(json_value, str):
        # This is a native Text concept - wrap it
        return {
            "concept": concept.concept_string,
            "content": json_value,
        }
    elif isinstance(json_value, (int, float)) and not isinstance(json_value, bool):
        # This is a native Number concept - wrap it
        return {
            "concept": concept.concept_string,
            "content": json_value,
        }
    elif isinstance(json_value, dict) and "concept" not in json_value:
        # Not yet wrapped with concept - wrap it now
        return {
            "concept": concept.concept_string,
            "content": json_value,
        }
    else:
        # Already has concept key or is properly formatted
        # At this point, json_value should be a dict with "concept" key
        return cast("dict[str, Any]", json_value)


def generate_input_memory_block_python(inputs: InputRequirements) -> str:
    """Generate just the Python input memory block (without surrounding code).

    Args:
        inputs: The pipe inputs

    Returns:
        Python code string representing the inputs dictionary
    """
    if inputs.nb_inputs == 0:
        return "{}"

    input_memory_entries: list[str] = []
    for var_name, input_req in inputs.root.items():
        concept = input_req.concept
        entry = generate_compact_memory_entry(var_name, concept)
        input_memory_entries.append(entry)

    # Join entries and format as a dictionary
    entries_str = "\n".join(input_memory_entries)
    return f"{{\n{entries_str}\n        }}"


def generate_input_memory_json(inputs: InputRequirements) -> dict[str, Any]:
    """Generate the input memory in pure JSON format.

    Args:
        inputs: The pipe inputs

    Returns:
        Dictionary with pure JSON values (no Python classes)
    """
    if inputs.nb_inputs == 0:
        return {}

    json_inputs: dict[str, Any] = {}
    for var_name, input_req in inputs.root.items():
        concept = input_req.concept
        json_value = generate_json_memory_entry(var_name, concept)
        json_inputs[var_name] = json_value

    return json_inputs


def generate_input_memory_json_string(inputs: InputRequirements, indent: int = 2) -> str:
    """Generate the input memory in pure JSON format as a formatted string.

    Args:
        inputs: The pipe inputs
        indent: Number of spaces for indentation (default: 2)

    Returns:
        Formatted JSON string
    """
    json_inputs = generate_input_memory_json(inputs)
    return json.dumps(json_inputs, indent=indent, ensure_ascii=False)


def generate_runner_code(pipe: PipeAbstract) -> str:
    """Generate the complete Python runner code for a pipe."""
    pipe_code = pipe.code
    inputs = pipe.inputs

    # Determine which imports are needed based on input concepts
    needs_pdf = False
    needs_image = False
    for input_req in inputs.root.values():
        concept = input_req.concept
        if concept.structure_class_name == "PDFContent":
            needs_pdf = True
        elif concept.structure_class_name == "ImageContent":
            needs_image = True

    # Build import section
    import_lines = ["import asyncio", ""]

    # Add content class imports if needed
    if needs_pdf:
        import_lines.append("from pipelex.core.stuffs.pdf_content import PDFContent")
    if needs_image:
        import_lines.append("from pipelex.core.stuffs.image_content import ImageContent")

    import_lines.extend(
        [
            "from pipelex.pipelex import Pipelex",
            "from pipelex.pipeline.execute import execute_pipeline",
        ]
    )

    # Build inputs entries
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
        "    return await execute_pipeline(",
        f'        pipe_code="{pipe_code}",',
    ]

    if inputs.nb_inputs > 0:
        function_lines.extend(
            [
                "        inputs={",
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
