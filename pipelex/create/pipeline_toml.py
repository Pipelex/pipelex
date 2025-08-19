from __future__ import annotations

from typing import Any, Dict, List, Mapping, cast

import tomlkit
from tomlkit import array, document, inline_table, table
from tomlkit import string as tk_string

from pipelex.tools.misc.json_utils import remove_none_values_from_dict
from pipelex.tools.misc.toml_utils import clean_trailing_whitespace


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


def _convert_to_inline(value: Any):
    """Recursively convert Python values; dicts -> inline tables; lists kept as arrays."""
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
        # Triple quotes if needed (or forced); closing quotes on their own line.
        return make_toml_string(
            value,
            prefer_literal=False,  # flip to True for '''...'''
            force_multiline=False,  # flip to True to force """...""" even without \n
            ensure_trailing_newline=True,  # keep closing """ on its own line
            ensure_leading_blank_line_in_value=False,  # flip to True to keep a blank first line
        )
    return value


def _convert_mapping_to_table(mapping: Mapping[str, Any]) -> Any:
    """Convert a mapping into a TOML Table where any nested mappings (third level+)
    are converted to inline tables.

    This creates a second-level standard table, and only uses inline tables for
    third level and deeper structures.
    """
    tbl = table()
    for field_key, field_value in mapping.items():
        if isinstance(field_value, Mapping):
            # Third-level mapping -> inline table
            tbl.add(field_key, _convert_to_inline(field_value))
        else:
            tbl.add(field_key, _convert_to_inline(field_value))
    return tbl


def dict_to_toml(data: Mapping[str, Any]) -> str:
    """Top-level keys become tables; second-level mappings become tables; inline tables start at third level."""
    data = remove_none_values_from_dict(data=data)
    document_root = document()
    for section_key, section_value in data.items():
        if isinstance(section_value, Mapping):
            section_value = cast(Mapping[str, Any], section_value)
            table_obj = table()
            for field_key, field_value in section_value.items():
                if isinstance(field_value, Mapping):
                    # Second level mapping -> standard table [section.field]
                    sub_table = _convert_mapping_to_table(cast(Mapping[str, Any], field_value))
                    table_obj.add(field_key, sub_table)
                else:
                    table_obj.add(field_key, _convert_to_inline(field_value))
            document_root.add(section_key, table_obj)  # `[section_key]` section
        else:
            document_root.add(section_key, _convert_to_inline(section_value))
    dumped_content = tomlkit.dumps(document_root)  # pyright: ignore[reportUnknownMemberType]
    return dumped_content


def save_toml_to_path(data: Dict[str, Any], path: str) -> None:
    """Save dictionary as TOML to file path.

    Args:
        data: Dictionary to save as TOML
        path: Path where to save the TOML file
    """
    # data_cleaned = remove_none_values_from_dict(data=data)
    data_cleaned = data
    with open(path, "w", encoding="utf-8") as file:
        toml_content: str = dict_to_toml(data=data_cleaned)
        cleaned_content = clean_trailing_whitespace(toml_content)
        file.write(cleaned_content)
