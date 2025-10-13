from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, cast

import tomlkit
from tomlkit import array, document, inline_table, table
from tomlkit import string as tomlkit_string

from pipelex import log
from pipelex.config import PlxConfig, get_config
from pipelex.tools.misc.json_utils import remove_none_values_from_dict
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint


class SectionKey(StrEnum):
    PIPE = "pipe"
    CONCEPT = "concept"


CONCEPT_STRUCTURE_FIELD_KEY = "structure"
PIPE_TEMPLATE_FIELD_KEY = "template"
PIPE_CATEGORY_FIELD_KEY = "pipe_category"


class PlxFactory:
    @classmethod
    def _plx_config(cls) -> PlxConfig:
        return get_config().pipelex.plx_config

    @classmethod
    def format_tomlkit_string(cls, text: str) -> Any:  # Can't type this because of tomlkit
        r"""Build a tomlkit string node.
        - If `force_multiline` or the text contains '\\n', we emit a triple-quoted multiline string.
        - When multiline, `ensure_trailing_newline` puts the closing quotes on their own line.
        - When multiline, `ensure_leading_blank_line` inserts a real blank line at the start of the string.
        """
        strings_config = cls._plx_config().strings

        needs_multiline = strings_config.force_multiline or ("\n" in text) or len(text) > strings_config.length_limit_to_multiline
        normalized = text

        if needs_multiline:
            if strings_config.ensure_leading_blank_line and not normalized.startswith("\n"):
                normalized = "\n" + normalized
            if strings_config.ensure_trailing_newline and not normalized.endswith("\n"):
                normalized = normalized + "\n"

        use_literal = strings_config.prefer_literal and ("'''" not in normalized)
        return tomlkit_string(normalized, multiline=needs_multiline, literal=use_literal)

    @classmethod
    def convert_dicts_to_inline_tables(cls, value: Any, field_ordering: list[str] | None = None) -> Any:  # Can't type this because of tomlkit
        """Recursively convert Python values; dicts -> inline tables; lists kept as arrays."""
        if isinstance(value, Mapping):
            value = cast("Mapping[str, Any]", value)
            inline_table_obj = inline_table()
            if field_ordering:
                for key in field_ordering:
                    if key in value:
                        inline_table_obj[key] = cls.convert_dicts_to_inline_tables(value=value[key])
            else:
                for key, value_item in value.items():
                    inline_table_obj[key] = cls.convert_dicts_to_inline_tables(value=value_item)
            return inline_table_obj

        elif isinstance(value, list):
            value = cast("list[Any]", value)
            array_obj = array()
            array_obj.multiline(True)  # set to False for single-line arrays
            for element in value:
                if isinstance(element, Mapping):
                    element = cast("Mapping[str, Any]", element)
                    inline_element = inline_table()
                    for inner_key, inner_value in element.items():
                        inline_element[inner_key] = cls.convert_dicts_to_inline_tables(value=inner_value)
                    array_obj.append(inline_element)  # pyright: ignore[reportUnknownMemberType]
                else:
                    array_obj.append(cls.convert_dicts_to_inline_tables(value=element))  # pyright: ignore[reportUnknownMemberType]
            return array_obj

        elif isinstance(value, str):
            return cls.format_tomlkit_string(text=value)
        else:
            return value

    @classmethod
    def convert_mapping_to_table(
        cls, mapping: Mapping[str, Any], field_ordering: list[str] | None = None
    ) -> Any:  # Can't type this because of tomlkit
        """Convert a mapping into a TOML Table where any nested mappings (third level+)
        are converted to inline tables.

        This creates a second-level standard table, and only uses inline tables for
        third level and deeper structures.

        Special case: template field is converted to a nested table section instead of inline.
        """
        tbl = table()

        # If field ordering is provided, add fields in the specified order first
        if field_ordering:
            for field_key in field_ordering:
                if field_key in mapping and field_key != PIPE_CATEGORY_FIELD_KEY:  # Skip category field (pipe metadata)
                    field_value = mapping[field_key]
                    if isinstance(field_value, Mapping):
                        # Special handling for template field - create nested table instead of inline
                        if field_key == PIPE_TEMPLATE_FIELD_KEY:
                            field_value = cast("Mapping[str, Any]", field_value)
                            tbl.add(field_key, cls.make_template_table(template_value=field_value))
                        else:
                            # Third-level mapping -> inline table
                            tbl.add(field_key, cls.convert_dicts_to_inline_tables(field_value))
                    else:
                        tbl.add(field_key, cls.convert_dicts_to_inline_tables(field_value))

            # Add any remaining fields not in the ordering
            for field_key, field_value in mapping.items():
                if field_key not in field_ordering and field_key != PIPE_CATEGORY_FIELD_KEY:
                    if isinstance(field_value, Mapping):
                        # Special handling for template field - create nested table instead of inline
                        if field_key == PIPE_TEMPLATE_FIELD_KEY:
                            field_value = cast("Mapping[str, Any]", field_value)
                            tbl.add(field_key, cls.make_template_table(template_value=field_value))
                        else:
                            # Third-level mapping -> inline table
                            tbl.add(field_key, cls.convert_dicts_to_inline_tables(field_value))
                    else:
                        tbl.add(field_key, cls.convert_dicts_to_inline_tables(field_value))
        else:
            # No field ordering provided, use original logic
            for field_key, field_value in mapping.items():
                # Skip the category field as it's not needed in PLX output (pipe metadata)
                if field_key == PIPE_CATEGORY_FIELD_KEY:
                    continue

                if isinstance(field_value, Mapping):
                    # Special handling for template field - create nested table instead of inline
                    if field_key == PIPE_TEMPLATE_FIELD_KEY:
                        field_value = cast("Mapping[str, Any]", field_value)
                        tbl.add(field_key, cls.make_template_table(template_value=field_value))
                    else:
                        # Third-level mapping -> inline table
                        tbl.add(field_key, cls.convert_dicts_to_inline_tables(field_value))
                else:
                    tbl.add(field_key, cls.convert_dicts_to_inline_tables(field_value))
        return tbl

    # TODO: replace this by a proper toml formatter utility
    @classmethod
    def add_spaces_to_inline_tables(cls, toml_string: str) -> str:
        """Add spaces inside inline table curly braces.

        Converts {key = value} to { key = value }.
        Only adds spaces if they're not already present.
        Handles nested inline tables properly.
        """

        def find_and_replace_inline_tables(text: str) -> str:
            """Find inline tables using proper brace matching and add spaces."""
            result = ""
            char_index = 0

            while char_index < len(text):
                if text[char_index] == "{":
                    # Check if this is a Jinja2 template (double braces)
                    if char_index + 1 < len(text) and text[char_index + 1] == "{":
                        # This is a Jinja2 template, find the closing }}
                        jinja_end = text.find("}}", char_index + 2)
                        if jinja_end != -1:
                            # Add the entire Jinja2 template as-is
                            result += text[char_index : jinja_end + 2]
                            char_index = jinja_end + 2
                            continue

                    # Found start of inline table, find the matching closing brace
                    brace_count = 1
                    start = char_index
                    char_index += 1

                    while char_index < len(text) and brace_count > 0:
                        if text[char_index] == "{":
                            brace_count += 1
                        elif text[char_index] == "}":
                            brace_count -= 1
                        char_index += 1

                    if brace_count == 0:
                        # Found complete inline table
                        content = text[start + 1 : char_index - 1]  # Content between braces

                        # Recursively process nested inline tables first
                        content = find_and_replace_inline_tables(content)

                        # Add spaces if not already present
                        if content.startswith(" ") and content.endswith(" "):
                            result += "{" + content + "}"
                        elif content.startswith(" "):
                            result += "{" + content + " }"
                        elif content.endswith(" "):
                            result += "{ " + content + "}"
                        else:
                            result += "{ " + content + " }"
                    else:
                        # Unmatched brace, add as-is
                        result += text[start:char_index]
                else:
                    result += text[char_index]
                    char_index += 1

            return result

        return find_and_replace_inline_tables(toml_string)

    @classmethod
    def make_template_table(cls, template_value: Mapping[str, Any]) -> Any:
        """Create a table for template fields, preserving all fields including category."""
        tbl = table()
        # For template, we want to keep all fields including 'category'
        # which has a different meaning than the pipe's category field
        for template_field_key, template_field_value in template_value.items():
            tbl.add(template_field_key, cls.convert_dicts_to_inline_tables(template_field_value))
        return tbl

    @classmethod
    def make_table_obj_for_pipe(cls, section_value: Mapping[str, Any]) -> Any:
        """Make a table object for a pipe section."""
        log.debug("******** Making table object for pipe section ********")
        table_obj = table()
        for field_key, field_value in section_value.items():
            log.debug(f"------ Field {field_key} is a {type(field_value)}")
            if not isinstance(field_value, Mapping):
                log.debug(f"Field is not a mapping: key = {field_key}, value = {field_value}")
                table_obj.add(field_key, cls.convert_dicts_to_inline_tables(field_value))
                continue
            log.debug(f"Field is a mapping: key = {field_key}, value = {field_value}")
            field_value = cast("Mapping[str, Any]", field_value)
            # Convert pipe configuration to table (handles template field specially)
            table_obj.add(field_key, cls.convert_mapping_to_table(field_value, field_ordering=cls._plx_config().pipes.field_ordering))
        return table_obj

    @classmethod
    def make_table_obj_for_concept(cls, section_value: Mapping[str, Any]) -> Any:
        """Make a table object for a concept section."""
        log.debug("******** Making table object for concept section ********")
        table_obj = table()
        for concept_key, concept_value in section_value.items():
            if isinstance(concept_value, str):
                log.debug(f"Concept '{concept_key}' is a string: {concept_value}")
                table_obj.add(concept_key, concept_value)
                continue
            if not isinstance(concept_value, Mapping):
                msg = f"Concept field value is not a mapping: key = {concept_key}, value = {concept_value}"
                raise TypeError(msg)
            log.debug(f"Concept '{concept_key}' is a mapping: {concept_value}")
            concept_value = cast("Mapping[str, Any]", concept_value)
            concept_table_obj = table()
            for concept_field_key, concept_field_value in concept_value.items():
                if concept_field_key == CONCEPT_STRUCTURE_FIELD_KEY:
                    if isinstance(concept_field_value, str):
                        log.debug(f"Structure for concept '{concept_key}' is a string: {concept_field_value}")
                        concept_table_obj.add("structure", concept_field_value)
                        continue
                    if not isinstance(concept_field_value, Mapping):
                        msg = f"Structure field value is not a mapping: key = {concept_field_key}, value = {concept_field_value}"
                        raise TypeError(msg)
                    log.debug(f"Structure for concept '{concept_key}' is a mapping: {concept_field_value}")
                    structure_value = cast("Mapping[str, Any]", concept_field_value)
                    structure_table_obj = table()
                    for structure_field_key, structure_field_value in structure_value.items():
                        if isinstance(structure_field_value, str):
                            log.debug(f"Structure '{structure_field_key}' is a string: {structure_field_value}")
                            structure_table_obj.add(structure_field_key, structure_field_value)
                            continue
                        if not isinstance(structure_field_value, Mapping):
                            msg = (
                                f"Structure field value is neither a string nor a mapping: "
                                f"key = {structure_field_key}, value = {structure_field_value}"
                            )
                            raise TypeError(msg)
                        log.debug(f"Structure for '{concept_key}' is a mapping: {structure_field_value}")
                        structure_table_obj.add(
                            structure_field_key,
                            cls.convert_dicts_to_inline_tables(
                                value=structure_field_value, field_ordering=cls._plx_config().concepts.structure_field_ordering
                            ),
                        )
                    concept_table_obj.add("structure", structure_table_obj)
                else:
                    # sub_table = _convert_mapping_to_table(concept_field_value)
                    log.debug(f"{concept_key}/'{concept_field_key}' is inline: {concept_field_value}")
                    concept_table_obj.add(concept_field_key, cls.convert_dicts_to_inline_tables(concept_field_value))
            table_obj.add(concept_key, concept_table_obj)
        return table_obj

    @classmethod
    def dict_to_plx_styled_toml(cls, data: Mapping[str, Any]) -> str:
        """Top-level keys become tables; second-level mappings become tables; inline tables start at third level."""
        log.debug("=" * 100)
        data = remove_none_values_from_dict(data=data)
        document_root = document()
        for root_key, root_value in data.items():
            if not isinstance(root_value, Mapping):
                log.debug(f"Root root_key is not a mapping: key = {root_key}, value = {root_value}")
                document_root.add(root_key, cls.convert_dicts_to_inline_tables(root_value))
                continue

            # It's a mapping, therefore it's a section
            log.debug(f"Root {root_key} is a section -------------------")

            section_key = SectionKey(root_key)
            section_value = cast("Mapping[str, Any]", root_value)
            # Skip empty mappings (empty concept and pipe sections)
            if not section_value:
                log.debug(f"Section {section_key} is empty, skipping")
                continue
            match section_key:
                case SectionKey.PIPE:
                    table_obj_for_pipe = cls.make_table_obj_for_pipe(section_value)
                    document_root.add(section_key, table_obj_for_pipe)
                case SectionKey.CONCEPT:
                    table_obj_for_concept = cls.make_table_obj_for_concept(section_value)
                    document_root.add(section_key, table_obj_for_concept)

        toml_output = tomlkit.dumps(document_root)  # pyright: ignore[reportUnknownMemberType]
        if cls._plx_config().inline_tables.spaces_inside_curly_braces:
            return cls.add_spaces_to_inline_tables(toml_output)
        return toml_output

    @classmethod
    def make_plx_content(cls, blueprint: PipelexBundleBlueprint) -> str:
        blueprint_dict = blueprint.model_dump(serialize_as_any=True)
        # blueprint_dict = cls._remove_pipe_category_from_pipes(blueprint_dict)
        return cls.dict_to_plx_styled_toml(data=blueprint_dict)
