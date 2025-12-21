import types
from typing import TYPE_CHECKING, Annotated, Any, Union, cast, get_args, get_origin

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


_NoneType = type(None)
_UnionType = getattr(types, "UnionType", None)  # Py3.10+: types.UnionType


def normalize_property_for_comparison(prop: dict[str, Any]) -> dict[str, Any]:
    """Normalize a property dict by removing description and keeping only structural parts.

    This recursively removes 'description' keys from the property dict, allowing
    structural comparison of JSON schemas that ignores field descriptions.

    Args:
        prop: A property dict from a JSON schema (e.g., {'type': 'string', 'description': 'A name'})

    Returns:
        The property dict with all 'description' keys removed at any nesting level.

    Example:
        >>> prop = {'type': 'string', 'description': 'The user name', 'title': 'Name'}
        >>> normalize_property_for_comparison(prop)
        {'type': 'string', 'title': 'Name'}

        >>> nested_prop = {'type': 'object', 'properties': {'id': {'type': 'integer', 'description': 'ID'}}}
        >>> normalize_property_for_comparison(nested_prop)
        {'type': 'object', 'properties': {'id': {'type': 'integer'}}}
    """
    normalized: dict[str, Any] = {}
    for key, value in prop.items():
        if key == "description":
            continue  # Skip descriptions for structural comparison
        if isinstance(value, dict):
            normalized[key] = normalize_property_for_comparison(cast("dict[str, Any]", value))
        else:
            normalized[key] = value
    return normalized


def normalize_properties_for_comparison(properties: dict[str, Any]) -> dict[str, Any]:
    """Normalize all properties in a schema for structural comparison.

    Applies normalize_property_for_comparison to each property in a JSON schema's
    'properties' dict, removing descriptions from all fields.

    Args:
        properties: The 'properties' dict from a JSON schema

    Returns:
        A new dict with all property descriptions removed.

    Example:
        >>> properties = {
        ...     'name': {'type': 'string', 'description': 'User name'},
        ...     'age': {'type': 'integer', 'description': 'User age'}
        ... }
        >>> normalize_properties_for_comparison(properties)
        {'name': {'type': 'string'}, 'age': {'type': 'integer'}}
    """
    return {name: normalize_property_for_comparison(prop) for name, prop in properties.items()}


def are_classes_equivalent(class_1: type[Any], class_2: type[Any]) -> bool:
    """Check if two Pydantic classes are structurally equivalent (same fields, types).

    This compares the structural parts of the JSON schema (properties, required fields, type)
    and ignores metadata like the class title/name and field descriptions.
    """
    if not (hasattr(class_1, "model_fields") and hasattr(class_2, "model_fields")):
        return class_1 == class_2

    # Compare model schemas using Pydantic's built-in capabilities
    try:
        schema_1: dict[str, Any] = class_1.model_json_schema()
        schema_2: dict[str, Any] = class_2.model_json_schema()

        # Compare required fields
        if schema_1.get("required") != schema_2.get("required"):
            return False

        # Compare type
        if schema_1.get("type") != schema_2.get("type"):
            return False

        # Compare properties, normalized to ignore descriptions
        props_1 = normalize_properties_for_comparison(schema_1.get("properties", {}))
        props_2 = normalize_properties_for_comparison(schema_2.get("properties", {}))
        if props_1 != props_2:
            return False

        # Compare $defs if present (for nested types)
        return schema_1.get("$defs") == schema_2.get("$defs")
    except Exception:
        # Fallback to manual field comparison if schema comparison fails
        fields_1: dict[str, FieldInfo] = class_1.model_fields
        fields_2: dict[str, FieldInfo] = class_2.model_fields

        if set(fields_1.keys()) != set(fields_2.keys()):
            return False

        for field_1_name, field_1_info in fields_1.items():
            field_1: FieldInfo = field_1_info
            field_2: FieldInfo = fields_2[field_1_name]

            # Compare field types
            if field_1.annotation != field_2.annotation:
                return False

            # Compare default values
            if field_1.default != field_2.default:
                return False

        return True


def has_compatible_field(class_1: type[Any], class_2: type[Any]) -> bool:
    """Check if class_1 has a field whose (possibly wrapped) type matches/subclasses class_2 or is structurally equivalent."""
    if not hasattr(class_1, "model_fields"):
        return False

    fields: dict[str, FieldInfo] = class_1.model_fields  # type: ignore[attr-defined]

    def _is_compatible(type_param: Any) -> bool:
        # Unwrap Annotated[T, ...]
        if get_origin(type_param) is Annotated:
            type_param = get_args(type_param)[0]

        origin = get_origin(type_param)

        # Handle unions, including PEP 604 (T | None)
        if origin in {Union, _UnionType}:
            for arg in get_args(type_param):
                if arg is _NoneType:
                    continue
                if _is_compatible(arg):
                    return True
            return False

        # Base case: direct match / subclass
        try:
            if type_param is class_2 or (isinstance(type_param, type) and issubclass(type_param, class_2)):
                return True
        except TypeError:
            # Not a class type (e.g., typing constructs you don't care about)
            pass

        # Also check for structural equivalence (same JSON schema)
        if isinstance(type_param, type) and hasattr(type_param, "model_fields"):
            if are_classes_equivalent(type_param, class_2):
                return True

        return False

    return any(_is_compatible(field.annotation) for field in fields.values())
