import ast
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import Field

from pipelex.core.concepts.concept_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.exceptions import ConceptStructureGeneratorError, PipelexException


class ConceptStructureValidationError(PipelexException):
    pass


class StructureGenerator:
    """Generate Pydantic BaseModel classes from concept structure blueprints."""

    # TODO: use StrEnum instead of Enum
    def __init__(self):
        self.imports = {
            "from typing import Optional, List, Dict, Any, Literal",
            "from enum import Enum",
            "from pipelex.core.stuffs.structured_content import StructuredContent",
            "from pydantic import Field",
        }
        self.enum_definitions: dict[str, dict[str, Any]] = {}  # Store enum definitions

    def generate_from_structure_blueprint(self, class_name: str, structure_blueprint: dict[str, ConceptStructureBlueprint]) -> tuple[str, type]:
        """Generate Python module content from structure blueprint.

        Args:
            class_name: Name of the class to generate
            structure_blueprint: Dictionary mapping field names to their ConceptStructureBlueprint definitions

        Returns:
            Generated Python module content, the generated class

        Raises:
            ConceptStructureGeneratorError: If the generated code is not syntactically correct or does not inherit from the required base class

        """
        # Generate the class
        class_code = self._generate_class_source_code_from_blueprint(class_name, structure_blueprint)

        # Generate the complete module
        imports_section = "\n".join(sorted(self.imports))

        generated_code = f"{imports_section}\n\n\n{class_code}\n"

        # Validate the generated code
        try:
            the_class = self.validate_generated_code(
                python_code=generated_code, expected_class_name=class_name, required_base_class=StructuredContent
            )
        except (ConceptStructureValidationError, SyntaxError, ValueError, ImportError, Exception) as exc:
            msg = f"Error validating generated code: {exc}"
            raise ConceptStructureGeneratorError(msg, structure_class_python_code=generated_code) from exc

        return generated_code, the_class

    def validate_generated_code(self, python_code: str, expected_class_name: str, required_base_class: type) -> type:
        """Validate that the generated Python code is syntactically correct and executable.

        Args:
            python_code: The generated Python code to validate
            expected_class_name: The name of the class that should be created
            required_base_class: The base class that the generated class should inherit from

        """
        ast.parse(python_code)

        compile(python_code, "<generated>", "exec")

        return self._validate_execution(
            python_code=python_code,
            expected_class_name=expected_class_name,
            required_base_class=required_base_class,
        )

    ############################################################
    # Private methods
    ############################################################

    def _format_default_value(self, value: Any) -> str:
        """Format default value for Python code, ensuring strings use double quotes."""
        if isinstance(value, str):
            return f'"{value}"'
        return repr(value)

    def _generate_class_source_code_from_blueprint(self, class_name: str, structure_blueprint: dict[str, ConceptStructureBlueprint]) -> str:
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
        field_definitions: list[str] = []
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
        field_params = [f'description="{field_blueprint.description}"']

        if field_blueprint.required:
            if field_blueprint.default_value is not None:
                field_params.insert(0, f"default={self._format_default_value(field_blueprint.default_value)}")
            else:
                field_params.insert(0, "...")
        elif field_blueprint.default_value is not None:
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
                    temp_blueprint = ConceptStructureBlueprint(description="temp", type=item_type_enum)
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
                    temp_blueprint = ConceptStructureBlueprint(description="temp", type=key_type_enum)
                    key_type = self._get_python_type_from_blueprint(temp_blueprint)
                except ValueError:
                    pass
                try:
                    value_type_enum = ConceptStructureBlueprintFieldType(value_type)
                    temp_blueprint = ConceptStructureBlueprint(description="temp", type=value_type_enum)
                    value_type = self._get_python_type_from_blueprint(temp_blueprint)
                except ValueError:
                    pass
                return f"Dict[{key_type}, {value_type}]"

    def _generate_field(self, field_name: str, field_def: dict[str, Any] | str) -> str:
        """Generate a single field definition.

        Args:
            field_name: Name of the field
            field_def: Field definition (dict or string for simple types)

        Returns:
            Generated field code

        """
        # Handle simple string definitions (just the definition text)
        if isinstance(field_def, str):
            field_def = {"type": ConceptStructureBlueprintFieldType.TEXT, "description": field_def}

        field_type = field_def.get("type", ConceptStructureBlueprintFieldType.TEXT)
        description = field_def.get("description", f"{field_name} field")
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
        field_params = [f'description="{description}"']

        if required:
            if default_value is not None:
                field_params.insert(0, f"default={self._format_default_value(default_value)}")
            else:
                field_params.insert(0, "...")
        elif default_value is not None:
            field_params.insert(0, f"default={self._format_default_value(default_value)}")
        else:
            field_params.insert(0, "default=None")

        field_call = f"Field({', '.join(field_params)})"

        return f"    {field_name}: {python_type} = {field_call}"

    def _get_python_type(self, field_type: Any, field_def: dict[str, Any]) -> str:
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

    def _validate_execution(self, python_code: str, expected_class_name: str, required_base_class: type) -> type:
        """Validate that the code executes and creates the expected class."""
        # Import necessary modules for the execution context
        from typing import Any  # noqa: PLC0415

        # Provide necessary imports in the execution context
        exec_globals = {
            "__builtins__": __builtins__,
            "datetime": datetime,
            "Enum": Enum,
            "Optional": Optional,
            "List": list,
            "Dict": dict,
            "Any": Any,
            "Literal": Literal,
            "Field": Field,
            "StructuredContent": StructuredContent,
        }
        exec_locals: dict[str, Any] = {}
        exec(python_code, exec_globals, exec_locals)

        # Verify the expected class was created
        if expected_class_name not in exec_locals:
            msg = f"Expected class '{expected_class_name}' not found in generated code"
            raise ConceptStructureValidationError(msg)

        the_class = exec_locals[expected_class_name]

        # Verify it's actually a class
        if not isinstance(the_class, type):
            msg = f"'{expected_class_name}' is not a class"
            raise ConceptStructureValidationError(msg)

        # Verify it inherits from the required base class
        if not issubclass(the_class, required_base_class):
            msg = f"'{expected_class_name}' does not inherit from {required_base_class.__name__}"
            raise ConceptStructureValidationError(msg)

        return the_class
