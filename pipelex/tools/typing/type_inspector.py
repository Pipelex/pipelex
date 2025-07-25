from enum import Enum
from typing import Any, Dict, List, Optional, Set, Type, Union, get_type_hints

from pydantic import BaseModel
from typing_extensions import get_args, get_origin

from pipelex.types import StrEnum


def pretty_type(tp: object) -> str:
    """Pretty print a type, with special handling for containers, literals and enums."""
    origin = getattr(tp, "__origin__", None)
    args = getattr(tp, "__args__", None)
    if origin is None:
        if isinstance(tp, type):
            return tp.__name__
        return str(tp)

    if origin is Union and args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and len(args) == 2:
            return f"Optional[{pretty_type(non_none[0])}]"
        return f"Union[{', '.join(pretty_type(a) for a in args)}]"

    if str(origin).endswith("Literal") and args:  # Handle both typing.Literal and typing_extensions.Literal
        # For enum values, just get their values
        values: List[str] = []
        for arg in args:
            if isinstance(arg, Enum) or isinstance(arg, StrEnum):
                values.append(f'"{arg.value}"')
            else:
                values.append(repr(arg))
        # Return multi-line format for Literal fields
        if len(values) > 1:
            return "Literal[\n        " + ",\n        ".join(values) + ",\n    ]"
        return f"Literal[{', '.join(values)}]"

    if (origin is list or origin is List) and args:
        return f"List[{pretty_type(args[0])}]"
    if (origin is dict or origin is Dict) and args:
        return f"Dict[{pretty_type(args[0])}, {pretty_type(args[1])}]"
    return str(tp)


def get_type_structure(
    tp: Type[Any],
    seen_types: Optional[Set[str]] = None,
    collected_types: Optional[Dict[str, Type[Any]]] = None,
    collected_enums: Optional[Dict[str, Type[Enum]]] = None,
    base_class: Type[Any] = BaseModel,
) -> List[str]:
    """
    Get the structure of a type, listing referenced subclasses of base_class and enums.

    Args:
        tp: The type to analyze
        seen_types: Set of already seen type names to avoid cycles
        collected_types: Dictionary of collected types to analyze
        collected_enums: Dictionary of collected enums
        base_class: The base class to check for inheritance (defaults to BaseModel)
    """
    if seen_types is None:
        seen_types = set()
    if collected_types is None:
        collected_types = {}
    if collected_enums is None:
        collected_enums = {}

    def format_type(tp: Any) -> str:
        """Format a type annotation nicely"""
        origin = get_origin(tp)
        if origin is None:
            if isinstance(tp, type):
                return tp.__name__
            return str(tp)

        args = get_args(tp)
        if origin is Union:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return f"Optional[{format_type(non_none[0])}]"
            return f"Union[{', '.join(format_type(a) for a in non_none)}]"

        if str(origin).endswith("Literal") and args:  # Handle both typing.Literal and typing_extensions.Literal
            # For enum values, just get their values
            values: List[str] = []
            enum_type = None
            for arg in args:
                if isinstance(arg, Enum) or isinstance(arg, StrEnum):
                    values.append(arg.value)
                    if enum_type is None:
                        enum_type = type(arg)
                else:
                    values.append(str(arg))
            # Add enum type to collected_enums if found
            if enum_type is not None:
                collected_enums[enum_type.__name__] = enum_type
            # Return multi-line format for Literal fields
            if len(values) > 1:
                lines: List[str] = []
                for value in values:
                    lines.append(f'"{value}"')
                return "Literal[\n        " + ",\n        ".join(lines) + ",\n    ]"
            return f"Literal[{', '.join(values)}]"

        if origin in (list, List):
            return f"List[{format_type(args[0])}]"
        if origin in (dict, Dict):
            return f"Dict[{format_type(args[0])}, {format_type(args[1])}]"
        return str(tp)

    def collect_types(tp: Type[Any]) -> None:
        """Recursively collect types and enums"""
        origin = get_origin(tp)
        args = get_args(tp)

        if origin:
            if origin is Union:
                non_none = [a for a in args if a is not type(None)]
                for arg in non_none:
                    if isinstance(arg, type):
                        collect_types(arg)
                    elif hasattr(arg, "__origin__"):  # Handle nested generics
                        collect_types(arg)
            elif origin in (list, List):
                if isinstance(args[0], type):
                    collect_types(args[0])
                elif hasattr(args[0], "__origin__"):  # Handle nested generics
                    collect_types(args[0])
            elif origin in (dict, Dict):
                for arg in args:
                    if isinstance(arg, type):
                        collect_types(arg)
                    elif hasattr(arg, "__origin__"):  # Handle nested generics
                        collect_types(arg)
            return

        # Collect enums
        if issubclass(tp, Enum) and tp not in collected_enums.values():
            collected_enums[tp.__name__] = tp
            return

        # Collect model classes
        if issubclass(tp, base_class) and tp.__name__ not in seen_types:
            seen_types.add(tp.__name__)
            collected_types[tp.__name__] = tp

            # Only collect immediate parent class if it's a custom class
            for base in tp.__bases__:
                if (
                    issubclass(base, BaseModel)
                    and base is not BaseModel
                    and base.__module__ != "pydantic.main"
                    and base.__module__ != "abc"
                    and not base.__module__.startswith("pipelex.core")
                ):
                    collect_types(base)

            try:
                type_hints = get_type_hints(tp)
                model_fields = getattr(tp, "model_fields", {})

                if model_fields:
                    for fname, _ in model_fields.items():
                        ftype = type_hints[fname]
                        collect_types(ftype)
                elif hasattr(tp, "__annotations__"):
                    for fname, ftype in type_hints.items():
                        collect_types(ftype)
            except (TypeError, AttributeError):
                # Handle cases where type hints cannot be retrieved
                pass

    # Start collection
    collect_types(tp)

    # Generate output
    output: List[str] = []

    # First output the main class and its dependencies
    for class_name, class_type in collected_types.items():
        if output:
            output.append("")

        # Get class docstring
        doc = class_type.__doc__ and class_type.__doc__.strip()
        base_class_name = class_type.__bases__[0].__name__

        # Get generic parameters if any
        type_args = get_args(class_type)
        if type_args:
            base_class_name = f"{base_class_name}[{', '.join(arg.__name__ for arg in type_args)}]"

        # Class definition with docstring
        output.append(f"class {class_name}({base_class_name}):")
        if doc:
            # Split docstring into lines and format each line
            doc_lines = [line.rstrip() for line in doc.split("\n")]

            # Remove empty lines from start and end
            while doc_lines and not doc_lines[0].strip():
                doc_lines.pop(0)
            while doc_lines and not doc_lines[-1].strip():
                doc_lines.pop()

            if len(doc_lines) == 1:
                # Single line docstring
                output.append(f'    """{doc_lines[0]}"""')
            else:
                # Multi-line docstring
                output.append(f'    """{doc_lines[0]}')

                # Add empty line after first line if there's content
                if doc_lines[1].strip():
                    output.append("")

                # Add remaining lines with proper indentation
                for line in doc_lines[1:]:
                    if line.strip():
                        output.append(f"    {line.strip()}")
                    else:
                        output.append("")

                # Close the docstring
                output.append('    """')

        # Handle empty classes or classes that only inherit fields
        try:
            type_hints = get_type_hints(class_type)
            model_fields = getattr(class_type, "model_fields", {})

            # Get and sort fields
            if model_fields:
                fields = model_fields.items()
            else:
                fields = [(type_k, type_hints[type_k]) for type_k in sorted(type_hints.keys())]

            # Check if all fields are inherited
            parent_fields: Set[str] = set()
            for base in class_type.__bases__:
                try:
                    parent_fields.update(get_type_hints(base).keys())
                except (TypeError, AttributeError):
                    continue

            current_fields = set(dict(fields).keys())
            non_inherited_fields = current_fields - parent_fields

            # Output fields
            for fname, ftype in fields:
                if fname in non_inherited_fields or (fname == "items" and "List" in base_class_name):
                    # Initialize is_optional to False by default
                    is_optional = False

                    if isinstance(ftype, type) and issubclass(ftype, BaseModel):
                        ftype_str = ftype.__name__
                    else:
                        field_type = type_hints[fname]
                        ftype_str = format_type(field_type)
                        # Check if field is Optional
                        field_origin = get_origin(field_type)
                        field_args = get_args(field_type)
                        is_optional = field_origin is Union and type(None) in field_args

                    # Handle default values
                    field_default = None
                    field_description = None
                    if model_fields:
                        field_info = model_fields.get(fname)
                        if field_info:
                            if hasattr(field_info, "default") and field_info.default is not None:
                                # Skip PydanticUndefined default values
                                if str(field_info.default) != "PydanticUndefined":
                                    field_default = field_info.default
                            if hasattr(field_info, "description"):
                                field_description = field_info.description

                    # Build the field line
                    field_line = f"    {fname}: {ftype_str}"
                    if is_optional:
                        field_line += " = None"
                    elif field_default is not None:
                        if isinstance(field_default, bool):
                            field_line += f" = {str(field_default)}"
                        elif not isinstance(field_default, (BaseModel, list, dict)):
                            field_line += f" = {repr(field_default)}"

                    # Add description as a comment if available
                    # First check if there's a direct field description from model_fields
                    if field_description:
                        field_line += f"  # {field_description}"
                    # Then check if the field type itself has model_fields and a description
                    # This handles nested content types that have field descriptions
                    elif hasattr(ftype, "model_fields") and fname in ftype.model_fields and hasattr(ftype.model_fields[fname], "description"):  # type: ignore
                        field_line += f"  # {ftype.model_fields[fname].description}"  # type: ignore

                    # Split multi-line field lines
                    if "\n" in field_line:
                        lines = field_line.split("\n")
                        output.extend(lines)
                    else:
                        output.append(field_line)
                    continue

            # If no fields were output, show inheritance comment
            if len(output) == (2 if doc else 1):
                output.append(f"    # Inherits from {base_class_name}")
                output.append("    # No additional fields")
        except (TypeError, AttributeError):
            # If we can't get type hints, show inheritance comment
            output.append(f"    # Inherits from {base_class_name}")
            output.append("    # No additional fields")

    # Then output all enum classes
    for enum_name, enum_type in collected_enums.items():
        if output:
            output.append("")
        output.append(f"class {enum_name}({enum_type.__bases__[0].__name__}):")
        # Add enum docstring if available, but skip Python's default "An enumeration." docstring
        # This ensures we only include meaningful custom docstrings
        if enum_type.__doc__ and enum_type.__doc__.strip() != "An enumeration.":
            doc = enum_type.__doc__.strip()
            output.append(f'    """{doc}"""')
        for member in enum_type:
            output.append(f'    {member.name} = "{member.value}"')

    return output
