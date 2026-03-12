"""Core operations for concept spec parsing and TOML generation."""

# pyright: reportUnknownMemberType=false

from typing import Any

import tomlkit

from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec


def parse_concept_spec(spec_data: dict[str, Any]) -> ConceptSpec:
    """Parse and validate a ConceptSpec from JSON-like data.

    Accepts common aliases for "the_concept_code" and converts structure fields.

    Args:
        spec_data: Raw data for the concept spec.

    Returns:
        Validated ConceptSpec instance.

    Raises:
        ValidationError: If validation fails.
    """
    # Accept common aliases for "the_concept_code"
    for alias in ("concept_code", "code", "name", "concept_name"):
        if alias in spec_data:
            if "the_concept_code" not in spec_data:
                spec_data["the_concept_code"] = spec_data.pop(alias)
            else:
                spec_data.pop(alias)

    # Convert structure if present - need to add field names
    if spec_data.get("structure"):
        structure_data = spec_data["structure"]
        converted_structure: dict[str, Any] = {}
        for field_name, field_data in structure_data.items():
            if isinstance(field_data, str):
                # Simple string means just description, default to text type
                converted_structure[field_name] = {
                    "the_field_name": field_name,
                    "description": field_data,
                    "type": "text",
                }
            else:
                # Full field spec
                field_data["the_field_name"] = field_name
                converted_structure[field_name] = field_data
        spec_data["structure"] = converted_structure

    return ConceptSpec.model_validate(spec_data)


def structure_field_to_dict(field_spec: ConceptStructureSpec) -> dict[str, Any]:
    """Convert a ConceptStructureSpec to a dictionary for TOML serialization.

    Args:
        field_spec: The field specification to convert.

    Returns:
        Dictionary with field properties.
    """
    result: dict[str, Any] = {}

    # Type is always needed unless it's just a text description
    if not field_spec.type.is_text or field_spec.required or field_spec.default_value is not None:
        result["type"] = field_spec.type

    result["description"] = field_spec.description

    if field_spec.required:
        result["required"] = True

    if field_spec.default_value is not None:
        result["default"] = field_spec.default_value

    if field_spec.concept_ref:
        result["concept_ref"] = field_spec.concept_ref

    if field_spec.choices:
        result["choices"] = field_spec.choices

    return result


def concept_spec_to_toml(concept_spec: ConceptSpec) -> str:
    """Convert a ConceptSpec to TOML string format.

    Args:
        concept_spec: The validated ConceptSpec to convert.

    Returns:
        TOML string representation of the concept.
    """
    doc = tomlkit.document()

    # Create the [concept.ConceptName] section
    concept_section = tomlkit.table()
    concept_item_table = tomlkit.table()

    # Add description
    concept_item_table.add("description", concept_spec.description)

    # Add refines if present
    if concept_spec.refines:
        concept_item_table.add("refines", concept_spec.refines)

    # Add structure if present
    if concept_spec.structure:
        structure_table = tomlkit.table()
        for field_name, field_spec in concept_spec.structure.items():
            field_dict = structure_field_to_dict(field_spec)
            # If only description is present, use simple string format
            if len(field_dict) == 1 and "description" in field_dict:
                structure_table.add(field_name, field_dict["description"])
            else:
                inline_table = tomlkit.inline_table()
                for key, value in field_dict.items():
                    inline_table.append(key, value)
                structure_table.add(field_name, inline_table)
        concept_item_table.add("structure", structure_table)

    # Build the nested structure: [concept.ConceptName]
    concept_section.add(concept_spec.the_concept_code, concept_item_table)
    doc.add("concept", concept_section)
    return tomlkit.dumps(doc)
