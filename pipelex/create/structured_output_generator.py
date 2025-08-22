"""Generate Pydantic BaseModel classes from concept structure blueprints for structured outputs."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from pipelex.core.concepts.concept_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType


class StructureGenerator:
    """Generate Pydantic BaseModel classes from concept structure blueprints."""

    def __init__(self):
        self.imports = {
            "from typing import Optional, List, Dict, Any, Literal",
            "from enum import Enum",
            "from pipelex.core.stuffs.stuff_content import StructuredContent",
            "from pydantic import Field",
        }
        self.enum_definitions: Dict[str, Dict[str, Any]] = {}  # Store enum definitions

    def _format_default_value(self, value: Any) -> str:
        """Format default value for Python code, ensuring strings use double quotes."""
        if isinstance(value, str):
            return f'"{value}"'
        else:
            return repr(value)

    def generate_from_structure_blueprint(self, class_name: str, structure_blueprint: Dict[str, ConceptStructureBlueprint]) -> str:
        """Generate Python module content from structure blueprint.

        Args:
            class_name: Name of the class to generate
            structure_blueprint: Dictionary mapping field names to their ConceptStructureBlueprint definitions

        Returns:
            Generated Python module content
        """
        # Generate the class
        class_code = self._generate_class_from_blueprint(class_name, structure_blueprint)

        # Generate the complete module
        imports_section = "\n".join(sorted(self.imports))

        return f"{imports_section}\n\n\n{class_code}\n"

    def _generate_class_from_blueprint(self, class_name: str, structure_blueprint: Dict[str, ConceptStructureBlueprint]) -> str:
        """Generate a class definition from ConceptStructureBlueprint.

        Args:
            class_name: Name of the class
            structure_blueprint: Dictionary mapping field names to their ConceptStructureBlueprint definitions

        Returns:
            Generated class code
        """
        # Generate class header
        class_header = f'class {class_name}(StructuredContent):\n    """Generated {class_name} class"""\n'

        # Generate fields
        field_definitions: List[str] = []
        for field_name, field_blueprint in structure_blueprint.items():
            field_code = self._generate_field_from_blueprint(field_name, field_blueprint)
            field_definitions.append(field_code)

        if not field_definitions:
            # Empty class with just pass
            return class_header + "\n    pass"

        fields_code = "\n".join(field_definitions)
        return class_header + "\n" + fields_code

    def _generate_field_from_blueprint(self, field_name: str, field_blueprint: ConceptStructureBlueprint) -> str:
        """Generate a field definition from ConceptStructureBlueprint.

        Args:
            field_name: Name of the field
            field_blueprint: ConceptStructureBlueprint instance

        Returns:
            Generated field code
        """
        # Determine Python type
        if field_blueprint.choices:
            # Inline choices - use Literal type
            python_type = f"Literal[{', '.join(repr(c) for c in field_blueprint.choices)}]"
        else:
            # Handle complex types
            python_type = self._get_python_type_from_blueprint(field_blueprint)

        # Make optional if not required
        if not field_blueprint.required:
            python_type = f"Optional[{python_type}]"

        # Generate Field parameters
        field_params = [f'description="{field_blueprint.definition}"']

        if field_blueprint.required:
            if field_blueprint.default_value is not None:
                field_params.insert(0, f"default={self._format_default_value(field_blueprint.default_value)}")
            else:
                field_params.insert(0, "...")
        else:
            if field_blueprint.default_value is not None:
                field_params.insert(0, f"default={self._format_default_value(field_blueprint.default_value)}")
            else:
                field_params.insert(0, "default=None")

        field_call = f"Field({', '.join(field_params)})"

        return f"    {field_name}: {python_type} = {field_call}"

    def _get_python_type_from_blueprint(self, field_blueprint: ConceptStructureBlueprint) -> str:
        """Convert ConceptStructureBlueprint to Python type annotation.

        Args:
            field_blueprint: ConceptStructureBlueprint instance

        Returns:
            Python type annotation string
        """
        if field_blueprint.type is None:
            # This should not happen based on validation, but handle gracefully
            return "str"

        # Use match/case for type handling
        match field_blueprint.type:
            case ConceptStructureBlueprintFieldType.TEXT:
                return "str"
            case ConceptStructureBlueprintFieldType.NUMBER:
                return "float"
            case ConceptStructureBlueprintFieldType.INTEGER:
                return "int"
            case ConceptStructureBlueprintFieldType.BOOLEAN:
                return "bool"
            case ConceptStructureBlueprintFieldType.DATE:
                self.imports.add("from datetime import datetime")
                return "datetime"
            case ConceptStructureBlueprintFieldType.LIST:
                item_type = field_blueprint.item_type or "Any"
                # Recursively handle item types if they're FieldType enums
                try:
                    item_type_enum = ConceptStructureBlueprintFieldType(item_type)
                    # Create a temporary blueprint for the item type
                    temp_blueprint = ConceptStructureBlueprint(definition="temp", type=item_type_enum)
                    item_type = self._get_python_type_from_blueprint(temp_blueprint)
                except ValueError:
                    # Keep as string if not a known FieldType
                    pass
                return f"List[{item_type}]"
            case ConceptStructureBlueprintFieldType.DICT:
                key_type = field_blueprint.key_type or "str"
                value_type = field_blueprint.value_type or "Any"
                # Recursively handle key and value types
                try:
                    key_type_enum = ConceptStructureBlueprintFieldType(key_type)
                    temp_blueprint = ConceptStructureBlueprint(definition="temp", type=key_type_enum)
                    key_type = self._get_python_type_from_blueprint(temp_blueprint)
                except ValueError:
                    pass
                try:
                    value_type_enum = ConceptStructureBlueprintFieldType(value_type)
                    temp_blueprint = ConceptStructureBlueprint(definition="temp", type=value_type_enum)
                    value_type = self._get_python_type_from_blueprint(temp_blueprint)
                except ValueError:
                    pass
                return f"Dict[{key_type}, {value_type}]"

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
                field_params.insert(0, f"default={self._format_default_value(default_value)}")
            else:
                field_params.insert(0, "...")
        else:
            if default_value is not None:
                field_params.insert(0, f"default={self._format_default_value(default_value)}")
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
            case ConceptStructureBlueprintFieldType.DATE:
                self.imports.add("from datetime import datetime")
                return "datetime"
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
