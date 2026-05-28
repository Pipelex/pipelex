"""Core operations for concept spec parsing and TOML generation."""

# pyright: reportUnknownMemberType=false

from typing import Any, cast

import tomlkit

from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptStructureSpec
from pipelex.builder.concept.exceptions import ConceptSpecError


def parse_concept_spec(spec_data: Any) -> ConceptSpec:
    """Parse and validate a ConceptSpec from JSON-like data.

    Accepts common aliases for "concept_code" and converts structure fields.

    Args:
        spec_data: Raw data for the concept spec (untrusted JSON-like input).

    Returns:
        Validated ConceptSpec instance.

    Raises:
        ConceptSpecError: If the top-level value is not a mapping, ``structure``
            is not a mapping, a structure field value is neither a description
            string nor a field-spec mapping, or a ConceptSpec-level rule fails
            (e.g. ``refines`` and ``structure`` both set). Carries the INPUT
            error domain.
        ValidationError: If Pydantic validation of the assembled spec fails.
    """
    # Validate the top-level shape before iterating so a non-mapping caller input
    # (scalar / list / None) surfaces as a typed, INPUT-domain ConceptSpecError
    # instead of a bare TypeError / ValueError from ``dict(...)`` below.
    if not isinstance(spec_data, dict):
        msg = f"Concept spec must be a mapping, got {type(spec_data).__name__}"
        raise ConceptSpecError(msg)
    spec_data = cast("dict[str, Any]", spec_data)

    # Work on a copy to avoid mutating the caller's dict
    spec_data = dict(spec_data)

    # Accept common aliases for "concept_code"
    for alias in ("the_concept_code", "code", "name", "concept_name", "concept_ref"):
        if alias in spec_data:
            if "concept_code" not in spec_data:
                spec_data["concept_code"] = spec_data.pop(alias)
            else:
                spec_data.pop(alias)

    # Convert structure if present - need to add field names.
    # Validate the raw shape before iterating so a malformed ``structure`` surfaces
    # as a typed, INPUT-domain ConceptSpecError instead of a bare AttributeError /
    # TypeError (which the caller cannot tell apart from a real programming bug).
    # ``is not None`` (not truthiness) so a present-but-falsy non-mapping — ``[]`` /
    # ``""`` / ``0`` / ``False`` — still hits the typed guard below instead of
    # silently skipping to a bare Pydantic ValidationError; ``None`` / absent both
    # mean "no structure" (the field defaults to ``None``).
    if spec_data.get("structure") is not None:
        structure_value = spec_data["structure"]
        if not isinstance(structure_value, dict):
            msg = f"Concept spec 'structure' must be a mapping of field names to field specs, got {type(structure_value).__name__}"
            raise ConceptSpecError(msg)
        structure_data = cast("dict[str, Any]", structure_value)
        converted_structure: dict[str, Any] = {}
        for field_name, field_data in structure_data.items():
            if isinstance(field_data, str):
                # Simple string means just description, default to text type
                converted_structure[field_name] = {
                    "the_field_name": field_name,
                    "description": field_data,
                    "type": "text",
                }
            elif isinstance(field_data, dict):
                # Full field spec — copy to avoid mutating nested caller data
                field_spec_data = dict(cast("dict[str, Any]", field_data))
                field_spec_data["the_field_name"] = field_name
                # Default to "text" when agent omits the type field
                if "type" not in field_spec_data:
                    field_spec_data["type"] = "text"
                converted_structure[field_name] = field_spec_data
            else:
                msg = (
                    f"Concept spec structure field '{field_name}' must be a description string or a field-spec mapping, "
                    f"got {type(field_data).__name__}"
                )
                raise ConceptSpecError(msg)
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
    concept_section.add(concept_spec.concept_code, concept_item_table)
    doc.add("concept", concept_section)
    return tomlkit.dumps(doc)
