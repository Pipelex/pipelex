import datetime
import inspect
import types
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin

from annotated_types import Ge, Gt, Le, Lt, MaxLen, MinLen, MultipleOf
from pydantic import BaseModel, PydanticUndefinedAnnotation, PydanticUserError
from pydantic.fields import FieldInfo
from pydantic.types import Strict
from pydantic_core import PydanticUndefined

_NoneType = type(None)
_UnionType = getattr(types, "UnionType", None)  # Py3.10+: types.UnionType

# The closed vocabulary of a "plain" model, the only kind the class-equivalence shortcut reads (see
# `_is_plain_model`). Every membership test against these tuples is by identity, so an annotation or a value
# that cannot be hashed, or a subclass carrying a pydantic hook of its own, is simply not a member.

# Leaf annotations whose JSON schema pydantic builds itself, with no hook a user could have attached.
_PLAIN_LEAF_ANNOTATIONS: tuple[Any, ...] = (str, int, float, bool, _NoneType, datetime.date, datetime.datetime, datetime.time, Any)
# Containers whose JSON schema is pydantic's own array or object over their item types, bare or subscripted.
_PLAIN_CONTAINER_TYPES: tuple[type[Any], ...] = (list, dict, set, tuple)
_UNION_ORIGINS: tuple[Any, ...] = (Union, types.UnionType)
_PLAIN_LITERAL_VALUE_TYPES: tuple[type[Any], ...] = (str, int, bool)
# Annotation markers that only add constraint keywords to the property they annotate, which is how pydantic
# stores `Field(gt=…, min_length=…, strict=…)` in `FieldInfo.metadata` too. Anything else (a `Field` nested in
# an `Annotated`, `SkipJsonSchema`, `WithJsonSchema`, a validator, a pattern) may rewrite or drop the property.
_INERT_METADATA_TYPES: tuple[type[Any], ...] = (Gt, Ge, Lt, Le, MultipleOf, MinLen, MaxLen, Strict)
# Values a field default may hold. Pydantic encodes a default into the schema through a `TypeAdapter` of the
# default's own type, whatever the field's annotation says, so a default of another type can run that type's
# hooks and drop the property.
_PLAIN_DEFAULT_SCALAR_TYPES: tuple[type[Any], ...] = (_NoneType, str, int, float, bool, datetime.date, datetime.datetime, datetime.time)
_PLAIN_DEFAULT_COLLECTION_TYPES: tuple[type[Any], ...] = (list, tuple, set, frozenset, dict)
# The class-level entry points to a model's JSON schema; a plain model inherits all three from `BaseModel`.
_MODEL_SCHEMA_ENTRY_POINTS = ("model_json_schema", "__get_pydantic_core_schema__", "__get_pydantic_json_schema__")


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


def _is_any_of(*, candidate: object, options: tuple[object, ...]) -> bool:
    """Whether `candidate` is one of `options`, by identity, so an unhashable candidate is simply not one."""
    return any(candidate is option for option in options)


def _has_one_of_types(*, value: object, allowed_types: tuple[type[Any], ...]) -> bool:
    """Whether the exact type of `value` is one of `allowed_types`; a subclass, which may carry a pydantic hook, is not."""
    return _is_any_of(candidate=type(value), options=allowed_types)


def _is_inherited_from_base_model(*, model_class: type[BaseModel], attribute_name: str) -> bool:
    """Whether `model_class` inherits `attribute_name` from `BaseModel` rather than defining its own."""
    for klass in model_class.__mro__:
        if attribute_name in vars(klass):
            return klass is BaseModel
    return False


def _is_plain_default(*, default_value: object) -> bool:
    """Whether a field default is built only from plain scalars and the builtin collections.

    A collection met twice (a shared or self-containing value) is refused rather than followed.
    """
    pending_values: list[object] = [default_value]
    seen_collection_ids: set[int] = set()
    while pending_values:
        value = pending_values.pop()
        if _has_one_of_types(value=value, allowed_types=_PLAIN_DEFAULT_SCALAR_TYPES):
            continue
        if not _has_one_of_types(value=value, allowed_types=_PLAIN_DEFAULT_COLLECTION_TYPES) or id(value) in seen_collection_ids:
            return False
        seen_collection_ids.add(id(value))
        if isinstance(value, dict):
            for item_key, item_value in cast("dict[object, object]", value).items():
                pending_values += [item_key, item_value]
        else:
            pending_values.extend(cast("list[object] | tuple[object, ...] | set[object] | frozenset[object]", value))
    return True


def _is_plain_annotation(*, annotation: Any, plain_or_pending_models: set[type[BaseModel]]) -> bool:
    """Whether an annotation is drawn from the plain vocabulary, recursing into its arguments and nested models."""
    origin = get_origin(annotation)
    if origin is None:
        if _is_any_of(candidate=annotation, options=_PLAIN_LEAF_ANNOTATIONS) or _is_any_of(candidate=annotation, options=_PLAIN_CONTAINER_TYPES):
            return True
        if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            return _is_plain_model(model_class=annotation, plain_or_pending_models=plain_or_pending_models)
        # A `TypeVar`, a `NewType`, a `TypeAliasType`, a forward reference, an enum, a dataclass, any other class.
        return False
    if origin is Literal:
        return all(_has_one_of_types(value=literal_value, allowed_types=_PLAIN_LITERAL_VALUE_TYPES) for literal_value in get_args(annotation))
    if origin is Annotated:
        base_annotation, *metadata = get_args(annotation)
        if not all(_has_one_of_types(value=metadata_item, allowed_types=_INERT_METADATA_TYPES) for metadata_item in metadata):
            return False
        return _is_plain_annotation(annotation=base_annotation, plain_or_pending_models=plain_or_pending_models)
    if _is_any_of(candidate=origin, options=_UNION_ORIGINS) or _is_any_of(candidate=origin, options=_PLAIN_CONTAINER_TYPES):
        return all(
            type_arg is Ellipsis or _is_plain_annotation(annotation=type_arg, plain_or_pending_models=plain_or_pending_models)
            for type_arg in get_args(annotation)
        )
    # A subscripted `TypeAliasType`, a parametrized generic class, `Callable`, the `collections.abc` generics.
    return False


def _is_plain_field(*, field_info: FieldInfo, plain_or_pending_models: set[type[BaseModel]]) -> bool:
    """Whether a field is published under its own name, whatever pydantic does with its schema."""
    if field_info.alias is not None or field_info.validation_alias is not None or field_info.serialization_alias is not None:
        return False
    if field_info.json_schema_extra is not None or field_info.field_title_generator is not None or field_info.discriminator is not None:
        return False
    if not all(_has_one_of_types(value=metadata_item, allowed_types=_INERT_METADATA_TYPES) for metadata_item in field_info.metadata):
        return False
    if field_info.default is not PydanticUndefined and not _is_plain_default(default_value=field_info.default):
        return False
    return _is_plain_annotation(annotation=field_info.annotation, plain_or_pending_models=plain_or_pending_models)


def _is_plain_model(*, model_class: type[BaseModel], plain_or_pending_models: set[type[BaseModel]]) -> bool:
    """Whether a model is plain: its validation-mode JSON schema provably publishes one property per field, named after it.

    Pydantic's `GenerateJsonSchema._named_required_fields_schema` (pydantic/json_schema.py) publishes, in the
    default validation mode, every field under its validation alias, except a field whose schema raises
    `PydanticOmit`. A plain model leaves no room for either: it keeps `BaseModel`'s own schema entry points, sets
    no model-level schema customisation (`json_schema_extra` in any form, a title generator, a mode override, an
    alias generator, `extra='allow'` with its typed extras), declares no validator input type, and every field
    has no alias, no field-level schema customisation, only inert constraint markers, a plain default and an
    annotation from a closed vocabulary — the scalars, `Any`, `Literal` of str, int or bool, unions, the
    builtin containers, `Annotated` with inert markers, and nested models that are plain in turn. That
    vocabulary is an allow-list on purpose: anything it does not name is "not known to be plain", never
    "known to omit".

    `plain_or_pending_models` holds the models already found plain and those still being checked, so that a
    model referring to itself terminates; a model under check counts as plain, which is sound because the walk
    stops at its first refusal and every answer that assumed it feeds into the verdict on that same model.
    """
    if model_class in plain_or_pending_models:
        return True
    plain_or_pending_models.add(model_class)
    if model_class.__pydantic_root_model__ or not model_class.__pydantic_complete__:
        return False
    if not all(_is_inherited_from_base_model(model_class=model_class, attribute_name=entry_point) for entry_point in _MODEL_SCHEMA_ENTRY_POINTS):
        return False
    model_config = model_class.model_config
    schema_shaping_settings = (
        model_config.get("json_schema_extra"),
        model_config.get("model_title_generator"),
        model_config.get("field_title_generator"),
        model_config.get("json_schema_mode_override"),
        model_config.get("alias_generator"),
    )
    if any(setting is not None for setting in schema_shaping_settings) or model_config.get("extra") == "allow":
        return False
    for field_validator in model_class.__pydantic_decorators__.field_validators.values():
        if field_validator.info.json_schema_input_type is not PydanticUndefined:
            return False
    return all(
        _is_plain_field(field_info=field_info, plain_or_pending_models=plain_or_pending_models) for field_info in model_class.model_fields.values()
    )


def _are_property_sets_certainly_different(*, class_1: type[Any], class_2: type[Any]) -> bool:
    """Whether the two classes certainly differ in which properties their JSON schemas publish, decided without generating one.

    It answers only for two plain models (see `_is_plain_model`), whose published property sets provably equal
    their field-name sets, so different field names mean different properties. Where the schema path cannot
    generate a schema, its field-by-field fallback compares those same field names, so both of
    `are_classes_equivalent`'s paths would say `False` too. `False` means "no shortcut", never "equivalent".
    """
    if not (inspect.isclass(class_1) and issubclass(class_1, BaseModel) and inspect.isclass(class_2) and issubclass(class_2, BaseModel)):
        return False
    if set(class_1.model_fields) == set(class_2.model_fields):
        return False
    return _is_plain_model(model_class=class_1, plain_or_pending_models=set()) and _is_plain_model(model_class=class_2, plain_or_pending_models=set())


def are_classes_equivalent(class_1: type[Any], class_2: type[Any]) -> bool:
    """Check if two Pydantic classes are structurally equivalent (same fields, types).

    This compares the structural parts of the JSON schema (properties, required fields, type)
    and ignores metadata like the class title/name and field descriptions.

    Generating a JSON schema is the expensive part, and two answers never need one. A class is
    equivalent to itself. And two plain models with different field names are not equivalent: a
    plain model is one built only from a closed vocabulary of types, constraints and settings (see
    `_is_plain_model`), for which the set of properties pydantic publishes provably equals the set of
    field names. Any pair that is not two plain models, or two plain models with the same field
    names, goes to the full schema comparison, which decides. Library validation asks the second
    question once per pipe output (is this concept an image?), so it is settled before any schema
    is generated.
    """
    if class_1 is class_2:
        return True

    if not (hasattr(class_1, "model_fields") and hasattr(class_2, "model_fields")):
        return class_1 == class_2

    if _are_property_sets_certainly_different(class_1=class_1, class_2=class_2):
        return False

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
    except (PydanticUserError, PydanticUndefinedAnnotation):
        # Fallback to manual field comparison if pydantic cannot generate a JSON schema for one of the classes
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


def are_structure_classes_compatible(*, class_1: type[Any], class_2: type[Any], strict: bool) -> bool:
    """Whether `class_1` can stand in for `class_2`, structurally.

    Structural equivalence always suffices. Beyond that, `strict` decides how much slack is allowed:
    strict mode accepts equivalence only, while loose mode also accepts a subclass relationship
    (a refined concept's generated class inherits from the refined one's) and a class that merely
    *carries* a compatible value in one of its fields — the "nested" case a template needs when it
    pulls an image out of a document.

    Pure over the two classes: it takes resolved types, never names, and reads no registry.
    """
    if are_classes_equivalent(class_1, class_2=class_2):
        return True

    if strict:
        return False

    try:
        if issubclass(class_1, class_2):
            return True
    except TypeError:
        # Not both classes (e.g. a typing construct slipped through) — fall through to field checks.
        pass

    return has_compatible_field(class_1, target_type=class_2)


def has_compatible_field(model_cls: type[Any], *, target_type: type[Any]) -> bool:
    """Check if model_cls has a field whose (possibly wrapped) type matches/subclasses target_type or is structurally equivalent."""
    if not hasattr(model_cls, "model_fields"):
        return False

    fields: dict[str, FieldInfo] = model_cls.model_fields  # type: ignore[attr-defined]

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
            if type_param is target_type or (isinstance(type_param, type) and issubclass(type_param, target_type)):
                return True
        except TypeError:
            # Not a class type (e.g., typing constructs you don't care about)
            pass

        # Also check for structural equivalence (same JSON schema)
        if isinstance(type_param, type) and hasattr(type_param, "model_fields"):
            if are_classes_equivalent(type_param, class_2=target_type):
                return True

        return False

    return any(_is_compatible(field.annotation) for field in fields.values())
