import re
import types
from enum import Enum, StrEnum
from typing import Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from pipelex.core.stuffs.stored_value_content import STORED_VALUE_REFERENCE_FIELDS, StoredValueContent
from pipelex.runtime_hub import get_class_registry
from pipelex.tools.misc.python_literals import class_docstring, escape_py_string

# A line break as Python source reads one, so that no line of a printed comment continues as code.
_SOURCE_LINE_BREAK = re.compile(r"\r\n|\r|\n")


def _value_literal(*, value: Any) -> str:
    """The Python literal of an enum member's or a `Literal` choice's value: an escaped string literal for a string."""
    if isinstance(value, str):
        return escape_py_string(value)
    return repr(value)


def _build_type_hints_namespace() -> dict[str, Any]:
    """Build a namespace for get_type_hints to resolve forward references.

    This is needed for dynamically generated classes (from StructureGenerator)
    that have forward references like `customer: "Customer"`. These classes
    don't have a proper module namespace, so get_type_hints() can't find the
    referenced types.

    We build a namespace by getting all classes from the class registry.

    Returns:
        A namespace dict with all registered classes
    """
    # Get all registered classes from the class registry
    # The root attribute is a dict[str, type] but the type checker doesn't know this
    class_registry = get_class_registry()
    root_dict: dict[str, Any] = getattr(class_registry, "root", {})
    return dict(root_dict)


class StructurePrinter:
    def pretty_type(self, tp: object) -> str:
        """Pretty print a type, with special handling for containers, literals and enums."""
        args = getattr(tp, "__args__", None)
        origin = get_origin(tp)
        if origin is None:
            if isinstance(tp, type):
                return tp.__name__
            return str(tp)

        args = get_args(tp)

        # was: if origin is Union and args:
        if origin in {Union, types.UnionType} and args:
            non_none = [a for a in args if a is not type(None)]
            if len(args) == 2 and len(non_none) == 1:
                return f"{self.pretty_type(non_none[0])} | None"
            return " | ".join(self.pretty_type(a) for a in args)

        if str(origin).endswith("Literal") and args:  # Handle both typing.Literal and typing_extensions.Literal
            # For enum values, just get their values
            values: list[str] = []
            for arg in args:
                if isinstance(arg, (Enum, StrEnum)):
                    values.append(_value_literal(value=arg.value))
                else:
                    values.append(_value_literal(value=arg))
            # Return multi-line format for Literal fields
            if len(values) > 1:
                return "Literal[\n        " + ",\n        ".join(values) + ",\n    ]"
            return f"Literal[{', '.join(values)}]"

        if origin is list and args:
            return f"List[{self.pretty_type(args[0])}]"
        if origin is dict and args:
            return f"Dict[{self.pretty_type(args[0])}, {self.pretty_type(args[1])}]"
        return str(tp)

    def get_type_structure(
        self,
        tp: type[Any],
        *,
        seen_types: set[str] | None = None,
        collected_types: dict[str, type[Any]] | None = None,
        collected_enums: dict[str, type[Enum]] | None = None,
        base_class: type[Any] = BaseModel,
    ) -> list[str]:
        """Get the structure of a type, listing referenced subclasses of base_class and enums.

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
            # was: if origin is Union:
            if origin in {Union, types.UnionType}:
                non_none = [a for a in args if a is not type(None)]
                if len(args) == 2 and len(non_none) == 1:
                    return f"{format_type(non_none[0])} | None"
                return " | ".join(format_type(a) for a in args)

            if str(origin).endswith("Literal") and args:  # Handle both typing.Literal and typing_extensions.Literal
                # For enum values, just get their values
                values: list[str] = []
                enum_type = None
                for arg in args:
                    if isinstance(arg, (Enum, StrEnum)):
                        values.append(_value_literal(value=arg.value))
                        if enum_type is None:
                            enum_type = type(arg)
                    else:
                        values.append(_value_literal(value=arg))
                # Add enum type to collected_enums if found
                if enum_type is not None:
                    collected_enums[enum_type.__name__] = enum_type
                # Return multi-line format for Literal fields
                if len(values) > 1:
                    return "Literal[\n        " + ",\n        ".join(values) + ",\n    ]"
                return f"Literal[{', '.join(values)}]"

            if origin is list:
                return f"List[{format_type(args[0])}]"
            if origin is dict:
                return f"Dict[{format_type(args[0])}, {format_type(args[1])}]"
            return str(tp)

        def collect_types(tp: type[Any]) -> None:
            """Recursively collect types and enums"""
            args = get_args(tp)

            origin = get_origin(tp)
            args = get_args(tp)

            if origin:
                # was: if origin is Union:
                if origin in {Union, types.UnionType}:
                    for arg in args:
                        if arg is type(None):
                            continue
                        if isinstance(arg, type) or get_origin(arg) is not None:
                            collect_types(arg)
                elif origin is list:
                    inner = args[0]
                    if isinstance(inner, type) or get_origin(inner) is not None:
                        collect_types(inner)
                elif origin is dict:
                    for arg in args:
                        if isinstance(arg, type) or get_origin(arg) is not None:
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
                        and base.__module__ not in {"pydantic.main", "abc"}
                        and not base.__module__.startswith("pipelex.core")
                    ):
                        collect_types(base)

                try:
                    # Build a namespace for get_type_hints to resolve forward references
                    # This is needed for dynamically generated classes (from StructureGenerator)
                    globalns = _build_type_hints_namespace()
                    type_hints = get_type_hints(tp, globalns=globalns)
                    model_fields = getattr(tp, "model_fields", {})

                    if model_fields:
                        for fname in model_fields:
                            ftype = type_hints[fname]
                            collect_types(ftype)
                    elif hasattr(tp, "__annotations__"):
                        for ftype in type_hints.values():
                            collect_types(ftype)
                except (TypeError, AttributeError):
                    # Handle cases where type hints cannot be retrieved
                    pass

        # Start collection
        collect_types(tp)

        # Generate output
        output: list[str] = []

        # First output the main class and its dependencies
        for class_name, class_type in collected_types.items():
            if output:
                output.append("")

            # Get class docstring, raw: stripping it would flatten the relative indentation of a body opening on a new line
            doc = class_type.__doc__
            base_class_name = class_type.__bases__[0].__name__

            # Get generic parameters if any
            type_args = get_args(class_type)
            if type_args:
                base_class_name = f"{base_class_name}[{', '.join(arg.__name__ for arg in type_args)}]"

            # Class definition with docstring, rendered so that no quote or backslash in it can close it early
            output.append(f"class {class_name}({base_class_name}):")
            if doc and doc.strip():
                output.extend(class_docstring(doc).split("\n"))
            class_header_length = len(output)

            # Handle empty classes or classes that only inherit fields
            try:
                # Build a namespace for get_type_hints to resolve forward references
                globalns = _build_type_hints_namespace()
                type_hints = get_type_hints(class_type, globalns=globalns)
                model_fields = getattr(class_type, "model_fields", {})

                # Get and sort fields
                if model_fields:
                    fields = model_fields.items()
                else:
                    fields = [(type_k, type_hints[type_k]) for type_k in sorted(type_hints.keys())]

                # Check if all fields are inherited
                parent_fields: set[str] = set()
                for base in class_type.__bases__:
                    try:
                        parent_fields.update(get_type_hints(base, globalns=globalns).keys())
                    except (TypeError, AttributeError):
                        continue

                current_fields = set(dict(fields).keys())
                printed_fields = current_fields - parent_fields

                # A model generating a content writes its value, never a reference to it, so a content that may hold its
                # value stored is printed as `generation_schema()` writes it: its value's fields, inherited ones included,
                # the value required, and none of the reference's fields.
                stored_value_field_name: str | None = None
                if issubclass(class_type, StoredValueContent):
                    stored_value_field_name = class_type.value_field_name
                    printed_fields = (printed_fields | set(class_type.value_form_field_names)) - set(STORED_VALUE_REFERENCE_FIELDS)

                # Output fields
                for fname, ftype in fields:
                    if fname in printed_fields or (fname == "items" and "List" in base_class_name):
                        # Initialize is_optional to False by default
                        is_optional = False

                        if isinstance(ftype, type) and issubclass(ftype, BaseModel):
                            ftype_str = ftype.__name__
                        else:
                            field_type = type_hints[fname]
                            field_origin = get_origin(field_type)
                            field_args = get_args(field_type)
                            is_union = field_origin in {Union, types.UnionType}

                            if fname == stored_value_field_name and is_union and type(None) in field_args:
                                ftype_str = " | ".join(format_type(field_arg) for field_arg in field_args if field_arg is not type(None))
                            else:
                                ftype_str = format_type(field_type)
                                is_optional = is_union and type(None) in field_args

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
                                field_line += f" = {field_default!s}"
                            elif not isinstance(field_default, (BaseModel, list, dict)):
                                field_line += f" = {field_default!r}"

                        # Add description as a comment if available
                        # First check if there's a direct field description from model_fields
                        comment: str | None = None
                        if field_description:
                            comment = field_description
                        # Then check if the field type itself has model_fields and a description
                        # This handles nested content types that have field descriptions
                        elif hasattr(ftype, "model_fields") and fname in ftype.model_fields and hasattr(ftype.model_fields[fname], "description"):  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
                            comment = f"{ftype.model_fields[fname].description}"  # pyright: ignore[reportUnknownMemberType]

                        # A multi-line Literal annotation spans several lines of its own
                        output.extend(field_line.split("\n"))
                        if comment is not None:
                            # Every line of the comment stays a comment, so none of it prints as code
                            first_comment_line, *continuation = _SOURCE_LINE_BREAK.split(comment)
                            output[-1] += f"  # {first_comment_line}"
                            output.extend(f"    # {comment_line}" for comment_line in continuation)
                        continue

                # If no fields were output, show inheritance comment
                if len(output) == class_header_length:
                    output.append("    # No additional fields")
            except (TypeError, AttributeError):
                # If we can't get type hints, show inheritance comment
                output.append("    # No additional fields")

        # Then output all enum classes
        for enum_name, enum_type in collected_enums.items():
            if output:
                output.append("")
            output.append(f"class {enum_name}({enum_type.__bases__[0].__name__}):")
            # Add enum docstring if available, but skip Python's default "An enumeration." docstring
            # This ensures we only include meaningful custom docstrings
            if enum_type.__doc__ and enum_type.__doc__.strip() != "An enumeration.":
                output.extend(class_docstring(enum_type.__doc__).split("\n"))
            output += [f"    {member.name} = {_value_literal(value=member.value)}" for member in enum_type]

        return output
