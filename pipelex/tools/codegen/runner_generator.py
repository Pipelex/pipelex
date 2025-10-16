"""Generate Python runner code from pipe definitions and concepts."""

from typing import Any


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
