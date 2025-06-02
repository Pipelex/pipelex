from enum import Enum
from typing import Any, Dict, List, Optional, Set, Type, Union, get_type_hints

from pydantic import BaseModel

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
    tp: object,
    seen_types: Optional[Set[str]] = None,
    collected: Optional[List[Type[Any]]] = None,
    base_class: Type[Any] = BaseModel,
) -> List[str]:
    """
    Get the structure of a type, listing referenced subclasses of base_class after the parent class.

    Args:
        tp: The type to analyze
        seen_types: Set of already seen type names to avoid cycles
        collected: List of collected types to analyze
        base_class: The base class to check for inheritance (defaults to BaseModel)
    """
    if seen_types is None:
        seen_types = set()
    if collected is None:
        collected = []

    def collect_types(tp: object):
        origin = getattr(tp, "__origin__", None)
        args = getattr(tp, "__args__", None)
        if origin and args:
            if origin is Union:
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    collect_types(non_none[0])
                else:
                    for arg in non_none:
                        collect_types(arg)
            elif origin in (list, List):
                collect_types(args[0])
            elif origin in (dict, Dict):
                collect_types(args[0])
                collect_types(args[1])
            return

        if isinstance(tp, type):
            if issubclass(tp, base_class) and tp.__name__ not in seen_types:
                seen_types.add(tp.__name__)
                collected.append(tp)
                type_hints = get_type_hints(tp)
                model_fields: Dict[str, Any] = getattr(tp, "model_fields", {})
                if model_fields:
                    for fname, _ in model_fields.items():
                        ftype = type_hints[fname]
                        collect_types(ftype)
                elif hasattr(tp, "__annotations__"):
                    for fname, ftype in type_hints.items():
                        collect_types(ftype)

    collect_types(tp)
    output: List[str] = []
    for idx, ctp in enumerate(collected):
        if idx > 0:
            output.append("")
        output.extend(pretty_print_class_structure(ctp))
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
