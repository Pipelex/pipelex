from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, cast

import toml
import tomlkit
from pydantic import BaseModel
from tomlkit import array, document, inline_table, table
from tomlkit import string as tk_string

from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.json_utils import remove_none_values_from_dict


class TOMLValidationError(Exception):
    """Raised when TOML file has formatting issues that could cause problems."""

    pass


def validate_toml_content(content: str, file_path: Optional[str] = None) -> None:
    """Validate TOML content for common formatting issues."""
    lines = content.splitlines()
    issues: List[str] = []

    for line_num, line in enumerate(lines, 1):
        # Check for trailing whitespace
        if line.rstrip() != line:
            trailing_chars = line[len(line.rstrip()) :]
            trailing_repr = repr(trailing_chars)
            issues.append(f"Line {line_num}: Trailing whitespace detected: {trailing_repr}")

        # Check for trailing whitespace after triple quotes (common issue)
        if line.strip().endswith('"""') and line != line.rstrip():
            issues.append(f"Line {line_num}: Trailing whitespace after triple quotes - this can cause TOML parsing issues")

    # Check for mixed line endings
    has_crlf = "\r\n" in content
    content_without_crlf = content.replace("\r\n", "")
    has_standalone_lf = "\n" in content_without_crlf
    if has_crlf and has_standalone_lf:
        issues.append("Mixed line endings detected (both CRLF and LF)")

    if issues:
        error_msg = f"TOML formatting issues in '{file_path}':\n" + "\n".join(f"  - {issue}" for issue in issues)
        raise TOMLValidationError(error_msg)


def validate_toml_file(path: str) -> None:
    """Validate TOML file for formatting issues.

    Args:
        path: Path to the TOML file to validate

    Raises:
        TOMLValidationError: If formatting issues are detected
    """
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
        validate_toml_content(content, path)


def clean_trailing_whitespace(content: str) -> str:
    """Clean trailing whitespace from TOML content.

    This function:
    1. Removes trailing whitespace from all lines
    2. Ensures exactly one empty line at EOF (two newline characters)
    3. If no empty line at EOF, removes trailing whitespace from last non-empty line

    Args:
        content: The TOML content to clean

    Returns:
        The cleaned TOML content with trailing whitespace removed and an empty line at EOF
    """
    # Split into lines and clean each line
    lines = [line.rstrip() for line in content.splitlines()]

    # Remove trailing empty lines
    while lines and not lines[-1]:
        lines.pop()

    # If we have lines and the last line has trailing whitespace, remove it
    if lines:
        lines[-1] = lines[-1].rstrip()

    # Join with newlines and ensure an empty line at EOF (two newlines)
    return "\n".join(lines) + "\n\n"


def load_toml_from_path(path: str) -> Dict[str, Any]:
    """Load TOML from path.

    Args:
        path: Path to the TOML file

    Returns:
        Dictionary loaded from TOML

    Raises:
        toml.TomlDecodeError: If TOML parsing fails, with file path included
    """
    try:
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()

        cleaned_content = clean_trailing_whitespace(content)

        # If content changed, write it back
        if content != cleaned_content:
            with open(path, "w", encoding="utf-8") as file:
                file.write(cleaned_content)

        dict_from_toml = toml.loads(cleaned_content)
        return dict_from_toml
    except toml.TomlDecodeError as exc:
        raise toml.TomlDecodeError(f"TOML parsing error in file '{path}': {exc}", exc.doc, exc.pos) from exc


def failable_load_toml_from_path(path: str) -> Optional[Dict[str, Any]]:
    """Load TOML from path with failure handling."""
    if not path_exists(path):
        return None
    try:
        return load_toml_from_path(path)
    except toml.TomlDecodeError as exc:
        print(f"Failed to parse TOML file '{path}': {exc}")
        return None


def make_toml_string(
    text: str,
    prefer_literal: bool = False,
    force_multiline: bool = False,
    ensure_trailing_newline: bool = True,
    ensure_leading_blank_line_in_value: bool = False,
):
    """
    Build a tomlkit string node.
    - If `force_multiline` or the text contains '\\n', we emit a triple-quoted multiline string.
    - When multiline, `ensure_trailing_newline` puts the closing quotes on their own line.
    - When multiline, `ensure_leading_blank_line_in_value` inserts a real blank line at the start of the value.
    """
    needs_multiline = force_multiline or ("\n" in text)
    normalized = text

    if needs_multiline:
        if ensure_leading_blank_line_in_value and not normalized.startswith("\n"):
            normalized = "\n" + normalized
        if ensure_trailing_newline and not normalized.endswith("\n"):
            normalized = normalized + "\n"

    use_literal = prefer_literal and ("'''" not in normalized)
    return tk_string(normalized, multiline=needs_multiline, literal=use_literal)


def _convert_to_inline(value: Any) -> Any:
    """Recursively convert Python values; dicts -> inline tables; lists kept as arrays."""
    # Handle Pydantic models by converting them to dict first
    if isinstance(value, BaseModel):
        # For RootModel, use the root attribute; for regular models, use model_dump()
        if hasattr(value, "root"):
            # This is a RootModel, use its root value
            value = getattr(value, "root")
        else:
            # This is a regular BaseModel, convert to dict
            value = value.model_dump()

    if isinstance(value, Mapping):
        value = cast(Mapping[str, Any], value)
        inline_table_obj = inline_table()
        for key, value_item in value.items():
            inline_table_obj[key] = _convert_to_inline(value_item)

        return inline_table_obj

    if isinstance(value, list):
        value = cast(List[Any], value)
        array_obj = array()
        array_obj.multiline(True)  # set to False for single-line arrays
        for element in value:
            if isinstance(element, Mapping):
                element = cast(Mapping[str, Any], element)
                inline_element = inline_table()
                for inner_key, inner_value in element.items():
                    inline_element[inner_key] = _convert_to_inline(inner_value)
                array_obj.append(inline_element)  # pyright: ignore[reportUnknownMemberType]
            else:
                array_obj.append(_convert_to_inline(element))  # pyright: ignore[reportUnknownMemberType]
        return array_obj

    if isinstance(value, str):
        # For prompt templates and similar fields, escape newlines instead of using multiline format
        if any(keyword in str(value) for keyword in ["@", "$"]) and "\n" in value:
            # This looks like a prompt template - escape newlines for single-line format
            # Return the string directly and let tomlkit handle the escaping properly
            return value
        else:
            # Triple quotes if needed (or forced); closing quotes on their own line.
            return make_toml_string(
                value,
                prefer_literal=False,  # flip to True for '''...'''
                force_multiline=False,  # flip to True to force """...""" even without \n
                ensure_trailing_newline=True,  # keep closing """ on its own line
                ensure_leading_blank_line_in_value=False,  # flip to True to keep a blank first line
            )
    return value


def _filter_empty_values(value: Any) -> Any:
    """Filter out empty lists and None values from data structures."""
    if isinstance(value, dict):
        filtered: Dict[str, Any] = {}
        for k, v in cast(Dict[str, Any], value).items():
            filtered_v = _filter_empty_values(v)
            # Keep empty dicts but skip empty lists and None values
            if filtered_v is not None and (not isinstance(filtered_v, list) or filtered_v):
                filtered[k] = filtered_v
        return filtered
    elif isinstance(value, list):
        return [_filter_empty_values(item) for item in cast(List[Any], value) if _filter_empty_values(item) is not None]
    else:
        return value


def _create_ordered_inline_table(data: Mapping[str, Any]) -> Any:
    """Create an inline table with fields in the expected order."""
    inline_table_obj = inline_table()

    # Define the preferred order for concept structure fields
    field_order = ["type", "definition", "required", "choices", "item_type", "key_type", "value_type"]

    # Add fields in preferred order first
    for field in field_order:
        if field in data:
            value = data[field]
            # Skip empty lists
            if isinstance(value, list) and not value:
                continue
            inline_table_obj[field] = _convert_to_inline(value)

    # Add any remaining fields not in the preferred order
    for key, value in data.items():
        if key not in field_order:
            # Skip empty lists
            if isinstance(value, list) and not value:
                continue
            inline_table_obj[key] = _convert_to_inline(value)

    return inline_table_obj


def dict_to_toml(data: Mapping[str, Any]) -> str:
    """Convert dictionary to TOML format matching Pipelex expectations."""
    data = remove_none_values_from_dict(data=data)
    data = _filter_empty_values(data)
    document_root = document()

    # Handle top-level fields first (domain, definition, system_prompt, etc.)
    for key, value in data.items():
        if not isinstance(value, Mapping):
            document_root.add(key, _convert_to_inline(value))

    # Handle sections (concepts, pipes)
    for section_key, section_value in data.items():
        if isinstance(section_value, Mapping):
            section_value = cast(Mapping[str, Any], section_value)

            # Skip empty sections
            if not section_value:
                continue

            # Create the section table
            section_table = table()

            # Process each item in the section
            for item_key, item_value in section_value.items():
                if isinstance(item_value, str):
                    # Simple string value (e.g., "SimpleData = 'Simple data concept'")
                    section_table.add(item_key, _convert_to_inline(item_value))
                elif isinstance(item_value, Mapping):
                    # Complex object that needs its own table
                    item_value = cast(Mapping[str, Any], item_value)
                    item_table = table()

                    # Handle the structure field specially
                    for field_key, field_value in item_value.items():
                        if field_key == "structure" and isinstance(field_value, Mapping):
                            # Structure should be its own table [section.item.structure]
                            structure_table = table()
                            for struct_key, struct_value in cast(Mapping[str, Any], field_value).items():
                                if isinstance(struct_value, Mapping):
                                    structure_table.add(struct_key, _create_ordered_inline_table(cast(Mapping[str, Any], struct_value)))
                                else:
                                    structure_table.add(struct_key, _convert_to_inline(struct_value))
                            item_table.add(field_key, structure_table)
                        else:
                            # Skip empty lists like refines = []
                            if isinstance(field_value, list) and not field_value:
                                continue
                            item_table.add(field_key, _convert_to_inline(field_value))

                    section_table.add(item_key, item_table)

            document_root.add(section_key, section_table)

    dumped_content = tomlkit.dumps(document_root)  # pyright: ignore[reportUnknownMemberType]

    # Post-process to fix inline table spacing: {key = "value"} -> { key = "value" }

    # Fix spacing around inline table contents - ensure single space after { and before }
    # This regex matches TOML inline tables (containing = signs) but not Jinja2 templates
    # We need to handle nested braces properly by working from innermost to outermost

    def fix_inline_table_spacing(content: str) -> str:
        """Fix spacing in inline tables, handling nested structures, but avoid modifying braces inside strings."""
        # Split content into lines and process each line
        lines = content.split("\n")
        processed_lines: list[str] = []

        for line in lines:
            # Only process lines that contain TOML inline tables (have '=' and braces outside quotes)
            # Skip lines that are just string values with braces (like Jinja2 templates)
            if "=" in line and "{" in line and "}" in line:
                # Check if this line has a TOML key-value assignment with inline table
                # Pattern: key = { ... } or key = { nested = { ... } }
                if re.match(r"^\s*\w+\s*=\s*\{", line):
                    # This is a TOML inline table assignment, apply spacing fixes
                    processed_line = line

                    # Apply multiple passes to handle nested structures properly
                    for _ in range(10):  # Prevent infinite loops
                        old_line = processed_line

                        # First: fix simple inline tables (no nested braces)
                        processed_line = re.sub(r"\{\s*([^{}]*=[^{}]*?)\s*\}", r"{ \1 }", processed_line)

                        # Second: fix nested inline tables - outer tables containing inner ones
                        # Match pattern like { key = { inner = "value" } }
                        processed_line = re.sub(r"\{\s*([^={}]*=\s*\{[^}]*\}[^{}]*?)\s*\}", r"{ \1 }", processed_line)

                        # Third: fix complex nested cases with multiple inner tables
                        # Handle cases like {key1 = {inner = "value"}, key2 = {inner2 = "value2"}}
                        processed_line = re.sub(r"\{\s*([^{}]*=\s*\{[^}]*\}.*?)\s*\}", r"{ \1 }", processed_line)

                        # Fourth: clean up any excessive whitespace that might remain
                        # Remove multiple consecutive spaces inside tables
                        processed_line = re.sub(r"\{\s*([^{}]*?)\s{2,}\}", r"{ \1 }", processed_line)

                        # Fifth: ensure consistent single space formatting
                        processed_line = re.sub(r"\{\s{2,}([^{}]*?)\s*\}", r"{ \1 }", processed_line)

                        if old_line == processed_line:
                            break

                    # Final cleanup: fix any remaining spacing issues in inline tables
                    # First: ensure there's a space between adjacent closing braces "}}"
                    processed_line = re.sub(r"\}\}", "} }", processed_line)

                    # Then: remove extra spaces (2 or more) before closing braces, but keep single spaces
                    # This pattern matches cases like "}  }" (2+ spaces) and replaces with "} }"
                    processed_line = re.sub(r"\}\s{2,}\}", "} }", processed_line)

                    processed_lines.append(processed_line)
                else:
                    # This line has braces but is not a TOML inline table (e.g., string with Jinja2)
                    # Leave it unchanged
                    processed_lines.append(line)
            else:
                # No braces or no assignment, leave unchanged
                processed_lines.append(line)

        return "\n".join(processed_lines)

    dumped_content = fix_inline_table_spacing(dumped_content)

    return dumped_content


def save_toml_to_path(data: Dict[str, Any], path: str) -> None:
    """Save dictionary as TOML to file path.

    Args:
        data: Dictionary to save as TOML
        path: Path where to save the TOML file
    """
    data_cleaned = data
    with open(path, "w", encoding="utf-8") as file:
        toml_content: str = dict_to_toml(data=data_cleaned)
        cleaned_content = clean_trailing_whitespace(toml_content)
        file.write(cleaned_content)
