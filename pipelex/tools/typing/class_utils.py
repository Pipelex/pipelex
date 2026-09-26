import dataclasses
import inspect
import types
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin

from annotated_types import GroupedMetadata
from pydantic import AliasChoices, AliasPath, BaseModel, PydanticUndefinedAnnotation, PydanticUserError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from typing_extensions import is_typeddict

_NoneType = type(None)
_UnionType = getattr(types, "UnionType", None)  # Py3.10+: types.UnionType

# The pydantic hooks through which a type or an annotation marker takes over its own schema. Any of them
# may raise `PydanticOmit`, which drops the enclosing property from the published JSON schema.
_SCHEMA_HOOK_NAMES = ("__get_pydantic_core_schema__", "__get_pydantic_json_schema__")


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


def _defines_schema_hook(*, candidate: Any) -> bool:
    """Whether a type or an annotation marker carries a pydantic schema hook of its own."""
    return any(hasattr(candidate, hook_name) for hook_name in _SCHEMA_HOOK_NAMES)


def _is_inherited_from_base_model(*, model_class: type[BaseModel], attribute_name: str) -> bool:
    """Whether `model_class` inherits `attribute_name` from `BaseModel` rather than defining its own."""
    for klass in model_class.__mro__:
        if attribute_name in vars(klass):
            return klass is BaseModel
    return False


def _has_default_schema_generation(*, model_class: type[BaseModel]) -> bool:
    """Whether `model_class` leaves JSON schema generation entirely to pydantic's own `BaseModel` code."""
    return all(
        _is_inherited_from_base_model(model_class=model_class, attribute_name=attribute_name)
        for attribute_name in ("model_json_schema", *_SCHEMA_HOOK_NAMES)
    )


def _may_metadata_omit_from_json_schema(*, metadata_item: Any) -> bool:
    """Whether an annotation marker could make pydantic omit the property it annotates from a JSON schema."""
    if isinstance(metadata_item, FieldInfo):
        # A `Field(...)` nested inside an inner `Annotated`: its schema edits apply where it sits.
        if callable(metadata_item.json_schema_extra):
            return True
        return any(_may_metadata_omit_from_json_schema(metadata_item=inner_item) for inner_item in metadata_item.metadata)
    if isinstance(metadata_item, GroupedMetadata):
        return any(_may_metadata_omit_from_json_schema(metadata_item=inner_item) for inner_item in metadata_item)
    # `SkipJsonSchema` and `WithJsonSchema(None)` are this shape, and so is every validator marker.
    return _defines_schema_hook(candidate=metadata_item)


def _may_class_omit_from_json_schema(*, candidate_class: type[Any]) -> bool:
    """Whether generating the JSON schema of a class could raise `PydanticOmit` into the field that uses it."""
    if issubclass(candidate_class, BaseModel):
        # A nested model's own fields cannot leak an omission: its field loop catches them. What reaches the
        # enclosing field is its class-level schema — its hooks, a callable `json_schema_extra` (a dict is only
        # merged in) and, for a root model, the root field's schema, which no field loop guards.
        return (
            not _has_default_schema_generation(model_class=candidate_class)
            or candidate_class.__pydantic_root_model__
            or callable(candidate_class.model_config.get("json_schema_extra"))
        )
    if dataclasses.is_dataclass(candidate_class) or is_typeddict(candidate_class) or hasattr(candidate_class, "_fields"):
        # Dataclasses, TypedDicts and NamedTuples carry per-member schemas this walk does not follow.
        return True
    return _defines_schema_hook(candidate=candidate_class)


def _may_omit_from_json_schema(*, annotation: Any) -> bool:
    """Whether pydantic could omit a property of this type from a model's JSON schema, conservatively.

    `GenerateJsonSchema._named_required_fields_schema` (pydantic/json_schema.py) drops a property whose schema
    raises `PydanticOmit`. Pydantic raises it for `SkipJsonSchema`, `WithJsonSchema(None)` and the `MISSING`
    sentinel, and any user hook may raise it too, so this walk answers `False` only for types built from things
    it can see through — generics, unions, `Literal`, `Annotated` with inert markers, classes without schema
    hooks, and models that leave their schema to pydantic. Anything else (a `TypeVar`, a forward reference, a
    sentinel, a hook) answers `True`, which means "cannot rule it out", not "it will".
    """
    origin = get_origin(annotation)
    if origin is Annotated:
        base_annotation, *metadata = get_args(annotation)
        if any(_may_metadata_omit_from_json_schema(metadata_item=metadata_item) for metadata_item in metadata):
            return True
        return _may_omit_from_json_schema(annotation=base_annotation)
    if origin is Literal:
        return False
    if origin is not None:
        if isinstance(origin, type) and _defines_schema_hook(candidate=origin):
            return True
        return any(_may_omit_from_json_schema(annotation=type_arg) for type_arg in get_args(annotation) if type_arg is not Ellipsis)
    if annotation is None:
        return False
    if isinstance(annotation, type):
        return _may_class_omit_from_json_schema(candidate_class=annotation)
    return True


def _published_field_name(*, field_name: str, field_info: FieldInfo) -> str | None:
    """The property name pydantic's validation-mode JSON schema gives a field, or `None` for an alias shape it cannot resolve.

    Mirrors `GenerateJsonSchema._get_alias_name` (pydantic/json_schema.py) exactly, fed the value the field's core
    schema carries — `_convert_to_aliases(field_info.validation_alias)` (pydantic/_internal/_generate_schema.py):
    a `str` alias is the name; an `AliasPath` converts to one flat path, which never matches, so the field name
    stands; an `AliasChoices` converts to a list of paths, and the first path that is exactly one string wins.
    An `alias_generator` needs no handling here: pydantic folds it into each `FieldInfo` when it collects the
    model's fields.
    """
    # Widened to `object` on purpose: an alias shape a later pydantic adds must be refused, not guessed at.
    validation_alias = cast("object", field_info.validation_alias)
    if validation_alias is None:
        return field_name
    if isinstance(validation_alias, str):
        return validation_alias
    if not isinstance(validation_alias, (AliasPath, AliasChoices)):
        return None
    for alias_path in validation_alias.convert_to_aliases():
        if isinstance(alias_path, list) and len(alias_path) == 1 and isinstance(alias_path[0], str):
            return alias_path[0]
    return field_name


def _published_property_names(*, model_class: type[Any]) -> frozenset[str] | None:
    """The property names `model_class.model_json_schema()` publishes, read off its fields, or `None` when that reading is not certain.

    `model_json_schema()` defaults to validation mode with `by_alias=True`, where every field is present and is
    published under its validation alias. The reading is refused for any model that can publish something else:
    one that overrides schema generation, a root model, one not yet complete, one whose `json_schema_extra` can
    rewrite the properties or whose `json_schema_mode_override` switches to serialization names, and one with a
    field pydantic could omit.
    """
    if not (inspect.isclass(model_class) and issubclass(model_class, BaseModel)):
        return None
    if not _has_default_schema_generation(model_class=model_class):
        return None
    if model_class.__pydantic_root_model__ or not model_class.__pydantic_complete__:
        return None
    model_config = model_class.model_config
    if model_config.get("json_schema_extra") is not None or model_config.get("json_schema_mode_override") is not None:
        return None
    # A validator's `json_schema_input_type` replaces the field's schema in validation mode, so it must be as
    # inert as the field's own annotation.
    for field_validator in model_class.__pydantic_decorators__.field_validators.values():
        json_schema_input_type = field_validator.info.json_schema_input_type
        if json_schema_input_type is not PydanticUndefined and _may_omit_from_json_schema(annotation=json_schema_input_type):
            return None

    published_names: set[str] = set()
    for field_name, field_info in model_class.model_fields.items():
        if callable(field_info.json_schema_extra):
            return None
        if any(_may_metadata_omit_from_json_schema(metadata_item=metadata_item) for metadata_item in field_info.metadata):
            return None
        if _may_omit_from_json_schema(annotation=field_info.annotation):
            return None
        published_name = _published_field_name(field_name=field_name, field_info=field_info)
        if published_name is None:
            return None
        published_names.add(published_name)
    return frozenset(published_names)


def _are_property_sets_certainly_different(*, model_class_1: type[Any], model_class_2: type[Any]) -> bool:
    """Whether the two models certainly differ in which properties they have, decided without generating a schema.

    `are_classes_equivalent` reaches its verdict by one of two paths — the JSON schemas, or the field-by-field
    fallback when pydantic cannot generate one — and this may answer `True` only where both would answer
    `False`. The schema path keys properties by published name and the fallback by field name, so the two
    models must differ under both namings. `False` means "no shortcut", never "equivalent".
    """
    published_names_1 = _published_property_names(model_class=model_class_1)
    if published_names_1 is None:
        return False
    published_names_2 = _published_property_names(model_class=model_class_2)
    if published_names_2 is None or published_names_1 == published_names_2:
        return False
    return set(model_class_1.model_fields) != set(model_class_2.model_fields)


def are_classes_equivalent(class_1: type[Any], class_2: type[Any]) -> bool:
    """Check if two Pydantic classes are structurally equivalent (same fields, types).

    This compares the structural parts of the JSON schema (properties, required fields, type)
    and ignores metadata like the class title/name and field descriptions.

    Generating a JSON schema is the expensive part, and two answers never need one: a class is
    equivalent to itself, and two models that certainly publish different property names are not
    equivalent. Library validation asks the second question once per pipe output (is this concept an
    image?), so both are settled before any schema is generated.
    """
    if class_1 is class_2:
        return True

    if not (hasattr(class_1, "model_fields") and hasattr(class_2, "model_fields")):
        return class_1 == class_2

    if _are_property_sets_certainly_different(model_class_1=class_1, model_class_2=class_2):
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
