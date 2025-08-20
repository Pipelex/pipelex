"""Generate Pydantic BaseModel classes from TOML definitions for structured outputs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import tomlkit

from pipelex.core.concepts.concept_blueprint import ConceptStructureBlueprintFieldType


class StructuredOutputGenerator:
    """Generate Pydantic BaseModel classes from TOML structured output definitions."""

    def __init__(self):
        self.imports = {
            "from typing import Optional, List, Dict, Any, Literal",
            "from enum import Enum",
            "from pipelex.core.stuffs.stuff_content import StructuredContent",
            "from pydantic import Field",
        }
        self.enum_definitions: Dict[str, Dict[str, Any]] = {}  # Store enum definitions

    def generate_from_toml(self, toml_content: str) -> str:
        """Generate Python module content from TOML structure and enum definitions.

        Args:
            toml_content: TOML content containing structure and enum definitions

        Returns:
            Generated Python module content
        """
        data = tomlkit.parse(toml_content)

        # Process enums first (if any)
        enums: List[str] = []
        if "enum" in data:
            enum_defs = data["enum"]
            for enum_name, enum_def in enum_defs.items():  # type: ignore[attr-defined,union-attr]
                self.enum_definitions[str(enum_name)] = dict(enum_def)  # type: ignore[arg-type]
                enum_code = self.generate_enum(str(enum_name), dict(enum_def))  # type: ignore[arg-type]
                enums.append(enum_code)

        # Process structures
        if "structure" not in data:
            raise ValueError("TOML must contain a 'structure' section")

        structures = data["structure"]
        classes: List[str] = []

        for class_name, structure_def in structures.items():  # type: ignore[attr-defined,union-attr]
            class_code = self.generate_class(str(class_name), dict(structure_def))  # type: ignore[arg-type]
            classes.append(class_code)

        # Generate the complete module
        imports_section = "\n".join(sorted(self.imports))

        # Combine enums and classes
        all_definitions: List[str] = []
        if enums:
            all_definitions.extend(enums)
        if classes:
            all_definitions.extend(classes)

        definitions_section = "\n\n\n".join(all_definitions)

        return f"{imports_section}\n\n\n{definitions_section}\n"

    def generate_enum(self, enum_name: str, enum_def: Dict[str, Any]) -> str:
        """Generate an enum class definition.

        Args:
            enum_name: Name of the enum
            enum_def: Enum definition from TOML

        Returns:
            Generated enum class code
        """
        definition = enum_def.get("definition", f"Generated {enum_name} enum")
        values: List[str] | Dict[str, str] = enum_def.get("values", [])

        # Generate enum header
        enum_header = f'class {enum_name}(str, Enum):\n    """{definition}"""\n'

        # Generate enum values
        value_definitions: List[str] = []

        if isinstance(values, list):
            # Simple list of values
            for value in values:
                # Convert to uppercase for enum member name
                value_str = str(value)
                member_name = value_str.upper().replace(" ", "_").replace("-", "_")
                value_definitions.append(f'    {member_name} = "{value_str}"')
        else:
            # Key-value pairs with descriptions
            for key, description in values.items():
                key_str = str(key)
                desc_str = str(description)
                member_name = key_str.upper().replace(" ", "_").replace("-", "_")
                value_definitions.append(f'    {member_name} = "{key_str}"  # {desc_str}')

        if not value_definitions:
            # Empty enum with just pass
            return enum_header + "\n    pass"

        values_code = "\n".join(value_definitions)
        return enum_header + "\n" + values_code

    def generate_class(self, class_name: str, structure_def: Dict[str, Any]) -> str:
        """Generate a single class definition.

        Args:
            class_name: Name of the class
            structure_def: Structure definition from TOML

        Returns:
            Generated class code
        """
        definition = structure_def.get("definition", f"Generated {class_name} class")
        fields = structure_def.get("fields", {})

        # Generate class header
        class_header = f'class {class_name}(StructuredContent):\n    """{definition}"""\n'

        # Generate fields
        field_definitions: List[str] = []
        for field_name, field_def in fields.items():
            field_code = self._generate_field(str(field_name), field_def)  # type: ignore[arg-type]
            field_definitions.append(field_code)

        if not field_definitions:
            # Empty class with just pass
            return class_header + "\n    pass"

        fields_code = "\n".join(field_definitions)
        return class_header + "\n" + fields_code

    def _generate_field(self, field_name: str, field_def: Union[Dict[str, Any], str]) -> str:
        """Generate a single field definition.

        Args:
            field_name: Name of the field
            field_def: Field definition (dict or string for simple types)

        Returns:
            Generated field code
        """
        # Handle simple string definitions (just the definition text)
        if isinstance(field_def, str):
            field_def = {"type": ConceptStructureBlueprintFieldType.TEXT, "definition": field_def}

        field_type = field_def.get("type", ConceptStructureBlueprintFieldType.TEXT)
        definition = field_def.get("definition", f"{field_name} field")
        required = field_def.get("required", False)
        default_value = field_def.get("default")
        choices = field_def.get("choices")  # For inline enum-like choices

        # Determine Python type
        if choices:
            # Inline choices - use Literal type
            python_type = f"Literal[{', '.join(repr(c) for c in choices)}]"
        else:
            # Handle complex types or enum references
            python_type = self._get_python_type(field_type, field_def)

        # Make optional if not required
        if not required:
            python_type = f"Optional[{python_type}]"

        # Generate Field parameters
        field_params = [f'description="{definition}"']

        if required:
            if default_value is not None:
                field_params.insert(0, f"default={repr(default_value)}")
            else:
                field_params.insert(0, "...")
        else:
            if default_value is not None:
                field_params.insert(0, f"default={repr(default_value)}")
            else:
                field_params.insert(0, "default=None")

        field_call = f"Field({', '.join(field_params)})"

        return f"    {field_name}: {python_type} = {field_call}"

    def _get_python_type(self, field_type: Any, field_def: Dict[str, Any]) -> str:
        """Convert high-level type to Python type annotation.

        Args:
            field_type: High-level type name or FieldType enum
            field_def: Complete field definition

        Returns:
            Python type annotation string
        """
        # Check if it's a reference to a defined enum
        if isinstance(field_type, str) and field_type in self.enum_definitions:
            return field_type

        # Convert string to FieldType if needed
        if isinstance(field_type, str):
            try:
                field_type_enum = ConceptStructureBlueprintFieldType(field_type)
            except ValueError:
                # Unknown type, assume it's a custom type or class reference
                return field_type
            field_type = field_type_enum

        # Use match/case for type handling
        match field_type:
            case ConceptStructureBlueprintFieldType.TEXT:
                return "str"
            case ConceptStructureBlueprintFieldType.NUMBER:
                return "float"
            case ConceptStructureBlueprintFieldType.INTEGER:
                return "int"
            case ConceptStructureBlueprintFieldType.BOOLEAN:
                return "bool"
            case ConceptStructureBlueprintFieldType.LIST:
                item_type = field_def.get("item_type", "Any")
                # Check if item_type is an enum reference
                if isinstance(item_type, str) and item_type in self.enum_definitions:
                    return f"List[{item_type}]"
                # Recursively handle item types
                if isinstance(item_type, str):
                    try:
                        item_type_enum = ConceptStructureBlueprintFieldType(item_type)
                        item_type = self._get_python_type(item_type_enum, {})
                    except ValueError:
                        # Keep as string if not a known FieldType
                        pass
                return f"List[{item_type}]"
            case ConceptStructureBlueprintFieldType.DICT:
                key_type = field_def.get("key_type", "str")
                value_type = field_def.get("value_type", "Any")
                # Recursively handle key and value types
                if isinstance(key_type, str):
                    try:
                        key_type_enum = ConceptStructureBlueprintFieldType(key_type)
                        key_type = self._get_python_type(key_type_enum, {})
                    except ValueError:
                        pass
                if isinstance(value_type, str):
                    try:
                        value_type_enum = ConceptStructureBlueprintFieldType(value_type)
                        value_type = self._get_python_type(value_type_enum, {})
                    except ValueError:
                        pass
                return f"Dict[{key_type}, {value_type}]"
            case _:
                # Unknown FieldType, assume it's a custom type
                return str(field_type)


def generate_structured_outputs_from_toml_file(toml_file_path: str, output_file_path: str) -> None:
    """Generate structured output Python module from TOML file.

    Args:
        toml_file_path: Path to input TOML file containing structure definitions
        output_file_path: Path to output Python file
    """
    with open(toml_file_path, "r", encoding="utf-8") as f:
        toml_content = f.read()

    generator = StructuredOutputGenerator()
    python_code = generator.generate_from_toml(toml_content)

    with open(output_file_path, "w", encoding="utf-8") as f:
        f.write(python_code)


def generate_structured_outputs_from_toml_string(toml_content: str) -> str:
    """Generate structured output Python code from TOML string.

    Args:
        toml_content: TOML content as string containing structure definitions

    Returns:
        Generated Python module content
    """
    generator = StructuredOutputGenerator()
    return generator.generate_from_toml(toml_content)


def generate_structured_output_from_inline_definition(
    class_name: str, fields_def: Dict[str, Any], enums: Optional[Dict[str, Dict[str, Any]]] = None
) -> str:
    """Generate structured output Python code from inline field definitions.

    Args:
        class_name: Name of the class to generate
        fields_def: Dictionary of field definitions (same format as TOML structure.fields)
        enums: Optional dictionary of enum definitions to include

    Returns:
        Generated Python module content
    """
    generator = StructuredOutputGenerator()

    # Add any provided enums
    if enums:
        for enum_name, enum_def in enums.items():
            generator.enum_definitions[enum_name] = enum_def

    # Create a structure definition from the inline fields
    structure_def = {"definition": f"Generated {class_name} structure", "fields": fields_def}

    # Generate the class
    class_code = generator.generate_class(class_name, structure_def)

    # Generate enums if any
    enum_codes: List[str] = []
    if enums:
        for enum_name, enum_def in enums.items():
            enum_code = generator.generate_enum(enum_name, enum_def)
            enum_codes.append(enum_code)

    # Combine everything
    imports_section = "\n".join(sorted(generator.imports))
    all_definitions: List[str] = enum_codes + [class_code] if enum_codes else [class_code]
    definitions_section = "\n\n\n".join(all_definitions)

    return f"{imports_section}\n\n\n{definitions_section}\n"
