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
                values.append(f"'{arg.value}'")
            else:
                values.append(repr(arg))
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
            elif origin in (list, List):
                if isinstance(args[0], type):
                    collect_types(args[0])
            elif origin in (dict, Dict):
                for arg in args:
                    if isinstance(arg, type):
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
            output.append(f'    """{doc}"""')

        # Handle empty classes or classes that only inherit fields
        try:
            type_hints = get_type_hints(class_type)
            model_fields = getattr(class_type, "model_fields", {})

            # Get and sort fields
            if model_fields:
                fields = model_fields.items()
            else:
                fields = [(k, type_hints[k]) for k in sorted(type_hints.keys())]

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
                    if isinstance(ftype, type) and issubclass(ftype, BaseModel):
                        ftype_str = ftype.__name__
                    else:
                        ftype_str = format_type(type_hints[fname])

                    # Handle default values
                    default = getattr(class_type, fname, None)
                    field_type = type_hints[fname]
                    origin = get_origin(field_type)
                    args = get_args(field_type)

                    # Check if field is Optional
                    is_optional = origin is Union and type(None) in args

                    if is_optional:
                        output.append(f"    {fname}: {ftype_str} = None")
                    elif default is not None and not isinstance(default, (BaseModel, list, dict)):
                        output.append(f"    {fname}: {ftype_str} = {repr(default)}")
                    else:
                        output.append(f"    {fname}: {ftype_str}")
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
        for member in enum_type:
            output.append(f'    {member.name} = "{member.value}"')

    return output


def pretty_print_class_structure(tp: Type[Any]) -> List[str]:
    lines: List[str] = []
    lines.append(f"Class '{tp.__name__}':")
    if tp.__doc__:
        lines.append(f"{tp.__doc__}")
    type_hints = get_type_hints(tp)
    model_fields: Dict[str, Any] = getattr(tp, "model_fields", {})
    if model_fields:
        for fname, f in model_fields.items():
            ftype = type_hints[fname]
            line = f"- {fname} ({pretty_type(ftype)})"
            if hasattr(f, "description") and getattr(f, "description", None):
                line += f": {f.description}"
            lines.append(line)
    elif hasattr(tp, "__annotations__"):
        for fname, ftype in type_hints.items():
            lines.append(f"- {fname} ({str(ftype)})")
    return lines
