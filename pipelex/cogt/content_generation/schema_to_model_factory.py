"""Rebuild a Pydantic class from the JSON schema of one, with `pydantic.create_model` and nothing else.

A structured-generation leaf hands the provider a class. In-process the caller's own class travels down beside the
assignment (see `object_class_resolution.resolve_object_class`) and this module is never reached. A worker that
received a serialized `ObjectAssignment` or `SearchObjectAssignment` holds only the class's JSON schema, so it rebuilds
the class here, and the rebuilt class's `model_json_schema()` is the schema it was rebuilt from: the provider is
constrained by the caller's schema, `Literal` fields hold their value, and constraints survive.

The schema always comes from a pipelex class's own `model_json_schema()`, so the builder accepts exactly the subset
pydantic emits for the classes pipelex builds and ships:

- objects with `properties`, `required`, `title`, `description` and `additionalProperties` (`true` is `extra="allow"`,
  `false` is `extra="forbid"`), and, on a property, an object whose `additionalProperties` is a schema or `true`, which
  is a `dict[str, …]` field;
- `$defs` with local `#/$defs/…` references, a root that is only a `$ref` included, and recursion through forward
  references resolved by one `model_rebuild` over the built classes; a definition is an object or an enumeration;
- `anyOf` as a union, `null` included, and a single-member `allOf` as its member;
- an inline string, integer or boolean `enum` or `const` as a `Literal`, and an enumeration in `$defs` as an `Enum`
  class of that name whose members are its values;
- `string` (with the formats `date`, `date-time`, `time` and `uri`), `integer`, `number`, `boolean` and `null`;
- arrays, with `uniqueItems` as a set;
- on a property, `title`, `description`, `examples`, `default` and the dry-run mock factory's `mock_format` hint;
- the constraints `exclusiveMinimum`, `minimum`, `exclusiveMaximum`, `maximum`, `multipleOf`,
  `minLength`, `maxLength`, `pattern`, `minItems` and `maxItems` as the matching `Field` arguments, wherever a type
  sits.

Anything else is refused with `UnsupportedSchemaError` naming where the schema left the subset: a shape outside it is a
pipelex defect to fix here, never a method author's. The builder carries its own guards, because the schema may cross
a process boundary: a cap on the number of nodes and on the nesting depth, checked before anything is built; a field
name must be an identifier that is no keyword, does not start with `_` and shadows none of pydantic's `model_…` API;
types come from a fixed table and from the classes the builder itself made from the schema's `$defs`, never from a
module, an attribute or the class registry a title names, so every class returned is a new one; and a forward reference
is an alias the builder chose, never a name the schema spelled, so no text of the schema is ever evaluated.
"""

import hashlib
import json
import keyword
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import date, datetime, time
from enum import Enum
from inspect import cleandoc
from types import GenericAlias
from typing import Annotated, Any, ClassVar, ForwardRef, Literal, Union, cast, get_args, get_origin

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, PydanticUserError, UrlConstraints, create_model
from pydantic.fields import FieldInfo
from pydantic_core import SchemaError

from pipelex.cogt.content_generation.exceptions import UnsupportedSchemaError

_LOCAL_REF_PREFIX = "#/$defs/"
# A forward reference the builder writes for a cycle: underscore-led, so no field name can shadow it.
_FORWARD_REF_PREFIX = "_schema_ref_"

_MODEL_KEYS = frozenset({"type", "properties", "required", "title", "description", "additionalProperties"})
_ENUM_DEF_KEYS = frozenset({"enum", "type", "title", "description"})
_PROPERTY_KEYS = frozenset({"title", "description", "default", "examples", "mock_format"})
_STRING_KEYS = frozenset({"type", "format", "minLength", "maxLength", "pattern"})
_NUMBER_KEYS = frozenset({"type", "exclusiveMinimum", "minimum", "exclusiveMaximum", "maximum", "multipleOf"})
_ARRAY_KEYS = frozenset({"type", "items", "uniqueItems", "minItems", "maxItems"})
_DICT_KEYS = frozenset({"type", "additionalProperties"})
_LITERAL_KEYS = frozenset({"type"})

_FORMAT_TYPES: dict[str, type[Any]] = {"date": date, "date-time": datetime, "time": time}
_LITERAL_VALUE_TYPES: dict[type[Any], str] = {str: "string", int: "integer", bool: "boolean"}
_NUMERIC_CONSTRAINTS = {"exclusiveMinimum": "gt", "minimum": "ge", "exclusiveMaximum": "lt", "maximum": "le", "multipleOf": "multiple_of"}
_LENGTH_CONSTRAINTS = {"minLength": "min_length", "maxLength": "max_length"}
_ITEM_CONSTRAINTS = {"minItems": "min_length", "maxItems": "max_length"}

# pydantic's own API on every model, which a field must not shadow: the builder calls `model_rebuild`, and every reader
# of a rebuilt class calls `model_json_schema`, `model_validate` or `model_dump`. pydantic v1's deprecated methods
# (`copy`, `dict`, `json`, `schema`, `validate` and the like) are not in it: a concept structure may name a field so, and
# pydantic lets a field shadow them, so the class rebuilt from that concept's schema has the field too.
_PYDANTIC_API_NAMES = frozenset(name for name in dir(BaseModel) if name.startswith("model_"))


def _doc_reading_back_as(*, description: str) -> str:
    """The `__doc__` whose `inspect.cleandoc` is `description`, which pydantic writes as the schema's description.

    A description pydantic wrote came out of `cleandoc` already, so it reads back unchanged unless its first line is
    indented or the lines after the first share an indentation, which `cleandoc` would strip. Set between line breaks,
    it leaves `cleandoc` no first line to treat apart and no indentation the lines share, so it reads back as it is.
    """
    if cleandoc(description) == description:
        return description
    return f"\n{description}\n"


def _refuse_unknown_keys(*, node: dict[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(key for key in node if key not in allowed)
    if unknown:
        msg = f"The schema at '{path}' carries {unknown}, which a class rebuilt from a schema does not support."
        raise UnsupportedSchemaError(msg)


def _refuse(*, path: str, reason: str) -> UnsupportedSchemaError:
    return UnsupportedSchemaError(f"The schema at '{path}' cannot be rebuilt into a class: {reason}.")


def _refuse_field_name(*, field_name: Any, path: str) -> None:
    reason: str | None = None
    if not isinstance(field_name, str) or not field_name.isidentifier():
        reason = "it is not an identifier"
    elif keyword.iskeyword(field_name):
        reason = "it is a Python keyword"
    elif field_name.startswith("_"):
        reason = "it starts with an underscore"
    elif field_name in _PYDANTIC_API_NAMES:
        reason = "it would shadow a method of every pydantic model"
    if reason is not None:
        msg = f"The schema at '{path}' names a property {field_name!r}, which cannot be a field name: {reason}."
        raise UnsupportedSchemaError(msg)


def _is_number(*, value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_count(*, value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


class _SchemaModelBuilder:
    """One rebuild: the classes made from one schema's `$defs`, and the forward references of its cycles."""

    MAX_NODES: ClassVar[int] = 10_000
    MAX_DEPTH: ClassVar[int] = 100

    def __init__(self, *, schema: dict[str, Any]) -> None:
        defs = schema.get("$defs", {})
        if not isinstance(defs, dict):
            raise _refuse(path="#/$defs", reason="it is not an object")
        self._defs = cast("dict[str, Any]", defs)
        self._built: dict[str, Any] = {}
        self._forward_refs: dict[str, str] = {}
        self._in_progress: set[str] = set()
        self._namespace: dict[str, Any] = {}
        self._models: list[type[BaseModel]] = []

    @classmethod
    def check_size(cls, *, schema: Any) -> None:
        """Refuse a schema past the node cap or the depth cap, walking it without recursion before anything reads it."""
        stack: list[tuple[Any, int]] = [(schema, 1)]
        node_count = 0
        while stack:
            node, depth = stack.pop()
            node_count += 1
            if node_count > cls.MAX_NODES:
                msg = f"The schema holds more than {cls.MAX_NODES} nodes, the most a class rebuilt from a schema may hold."
                raise UnsupportedSchemaError(msg)
            if depth > cls.MAX_DEPTH:
                msg = f"The schema nests deeper than {cls.MAX_DEPTH} levels, the most a class rebuilt from a schema may nest."
                raise UnsupportedSchemaError(msg)
            if isinstance(node, dict):
                stack.extend((child, depth + 1) for child in cast("dict[str, Any]", node).values())
            elif isinstance(node, list):
                stack.extend((child, depth + 1) for child in cast("list[Any]", node))

    def build(self, *, schema: dict[str, Any], class_name: str) -> type[BaseModel]:
        root: type[BaseModel]
        if "$ref" in schema:
            _refuse_unknown_keys(node=schema, allowed=frozenset({"$ref", "$defs"}), path="#")
            referenced = self._reference(ref=schema["$ref"], depth=1, path="#/$ref")
            if not (isinstance(referenced, type) and issubclass(referenced, BaseModel)):
                raise _refuse(path="#/$ref", reason="the root references no object")
            root = referenced
        else:
            root = self._model(node=schema, fallback_name=class_name, depth=1, path="#", allowed_keys=_MODEL_KEYS | {"$defs"})
        for model in self._models:
            if not model.__pydantic_complete__:
                try:
                    model.model_rebuild(_types_namespace=self._namespace)
                except (PydanticUserError, SchemaError) as exc:
                    msg = f"The class '{model.__name__}' rebuilt from the schema did not resolve its references: {exc}"
                    raise UnsupportedSchemaError(msg) from exc
        return root

    def _count_depth(self, *, depth: int, path: str) -> None:
        # The size check bounds the schema itself; references can still chain definitions deeper than it nests.
        if depth > self.MAX_DEPTH:
            raise _refuse(path=path, reason=f"its references chain deeper than {self.MAX_DEPTH} levels")

    def _model(self, *, node: Any, fallback_name: str, depth: int, path: str, allowed_keys: frozenset[str] = _MODEL_KEYS) -> type[BaseModel]:
        self._count_depth(depth=depth, path=path)
        if not isinstance(node, dict):
            raise _refuse(path=path, reason="it is not an object")
        model_node = cast("dict[str, Any]", node)
        _refuse_unknown_keys(node=model_node, allowed=allowed_keys, path=path)
        if model_node.get("type") != "object":
            raise _refuse(path=path, reason="a definition is an object or an enumeration")
        title = model_node.get("title", fallback_name)
        description = model_node.get("description")
        properties = model_node.get("properties", {})
        required = model_node.get("required", [])
        if not isinstance(title, str) or not title:
            raise _refuse(path=f"{path}/title", reason="the title is not a string")
        if description is not None and not isinstance(description, str):
            raise _refuse(path=f"{path}/description", reason="the description is not a string")
        if not isinstance(properties, dict):
            raise _refuse(path=f"{path}/properties", reason="the properties are not an object")
        properties = cast("dict[str, Any]", properties)
        if not isinstance(required, list) or any(name not in properties for name in cast("list[Any]", required)):
            raise _refuse(path=f"{path}/required", reason="the required names are not a list of its properties")
        required_names = set(cast("list[str]", required))

        config: ConfigDict | None
        match model_node.get("additionalProperties"):
            case None:
                config = None
            case True:
                config = ConfigDict(extra="allow")
            case False:
                config = ConfigDict(extra="forbid")
            case _:
                raise _refuse(path=f"{path}/additionalProperties", reason="an object's extra properties are allowed or forbidden, never typed")

        fields: dict[str, Any] = {}
        for field_name, field_node in properties.items():
            field_path = f"{path}/properties/{field_name}"
            _refuse_field_name(field_name=field_name, path=field_path)
            fields[field_name] = self._field(node=field_node, is_required=field_name in required_names, depth=depth + 1, path=field_path)

        try:
            model = create_model(
                title,
                __config__=config,
                __doc__=_doc_reading_back_as(description=description) if description else None,
                __module__="builtins",
                **fields,
            )
        except (PydanticUserError, SchemaError, TypeError) as exc:
            msg = f"The schema at '{path}' did not build into a class: {exc}"
            raise UnsupportedSchemaError(msg) from exc
        self._models.append(model)
        return model

    def _field(self, *, node: Any, is_required: bool, depth: int, path: str) -> tuple[Any, FieldInfo]:
        if not isinstance(node, dict):
            raise _refuse(path=path, reason="the property is not an object")
        field_node = cast("dict[str, Any]", node)
        type_node = {key: value for key, value in field_node.items() if key not in _PROPERTY_KEYS}
        annotation = self._annotation(node=type_node, depth=depth, path=path)
        field_kwargs: dict[str, Any] = {}
        for key in ("title", "description"):
            if key in field_node:
                if not isinstance(field_node[key], str):
                    raise _refuse(path=f"{path}/{key}", reason=f"the {key} is not a string")
                field_kwargs[key] = field_node[key]
        if "examples" in field_node:
            if not isinstance(field_node["examples"], list):
                raise _refuse(path=f"{path}/examples", reason="the examples are not a list")
            field_kwargs["examples"] = field_node["examples"]
        if "mock_format" in field_node:
            # The dry-run mock factory's hint, which pydantic writes from `json_schema_extra`; the factory reads it back.
            if not isinstance(field_node["mock_format"], str):
                raise _refuse(path=f"{path}/mock_format", reason="the mock format is not a string")
            field_kwargs["json_schema_extra"] = {"mock_format": field_node["mock_format"]}
        if "default" in field_node:
            return annotation, Field(default=field_node["default"], **field_kwargs)
        if is_required:
            return annotation, Field(**field_kwargs)
        # A field that is not required yet shows no default had a default factory, which the schema does not describe:
        # a container starts empty, as its factory almost always made it, and anything else starts as nothing.
        return annotation, Field(default_factory=_empty_value_factory(annotation=annotation), **field_kwargs)

    def _annotation(self, *, node: Any, depth: int, path: str) -> Any:
        self._count_depth(depth=depth, path=path)
        if not isinstance(node, dict):
            raise _refuse(path=path, reason="a type is described by an object")
        type_node = cast("dict[str, Any]", node)
        if "$ref" in type_node:
            _refuse_unknown_keys(node=type_node, allowed=frozenset({"$ref"}), path=path)
            return self._reference(ref=type_node["$ref"], depth=depth + 1, path=f"{path}/$ref")
        if "anyOf" in type_node:
            _refuse_unknown_keys(node=type_node, allowed=frozenset({"anyOf"}), path=path)
            members = type_node["anyOf"]
            if not isinstance(members, list) or not members:
                raise _refuse(path=f"{path}/anyOf", reason="a union lists its members")
            member_types = tuple(
                self._annotation(node=member, depth=depth + 1, path=f"{path}/anyOf/{index_member}")
                for index_member, member in enumerate(cast("list[Any]", members))
            )
            return Union[member_types]
        if "allOf" in type_node:
            _refuse_unknown_keys(node=type_node, allowed=frozenset({"allOf"}), path=path)
            members = type_node["allOf"]
            if not isinstance(members, list) or len(cast("list[Any]", members)) != 1:
                raise _refuse(path=f"{path}/allOf", reason="only an allOf of one member is supported")
            return self._annotation(node=cast("list[Any]", members)[0], depth=depth + 1, path=f"{path}/allOf/0")
        if "const" in type_node:
            _refuse_unknown_keys(node=type_node, allowed=_LITERAL_KEYS | {"const"}, path=path)
            return Literal[self._literal_values(values=[type_node["const"]], node=type_node, path=path)]
        if "enum" in type_node:
            _refuse_unknown_keys(node=type_node, allowed=_LITERAL_KEYS | {"enum"}, path=path)
            return Literal[self._literal_values(values=type_node["enum"], node=type_node, path=path)]

        match type_node.get("type"):
            case None:
                _refuse_unknown_keys(node=type_node, allowed=frozenset(), path=path)
                return Any
            case "string":
                return self._string(node=type_node, path=path)
            case "integer":
                return self._constrained(base=int, node=type_node, keys=_NUMBER_KEYS, path=path)
            case "number":
                return self._constrained(base=float, node=type_node, keys=_NUMBER_KEYS, path=path)
            case "boolean":
                _refuse_unknown_keys(node=type_node, allowed=frozenset({"type"}), path=path)
                return bool
            case "null":
                _refuse_unknown_keys(node=type_node, allowed=frozenset({"type"}), path=path)
                return None
            case "array":
                return self._array(node=type_node, depth=depth, path=path)
            case "object":
                return self._dict(node=type_node, depth=depth, path=path)
            case other_type:
                raise _refuse(path=f"{path}/type", reason=f"the type {other_type!r} is not supported")

    def _literal_values(self, *, values: Any, node: dict[str, Any], path: str) -> tuple[Any, ...]:
        if not isinstance(values, list) or not values:
            raise _refuse(path=path, reason="an enumeration lists its values")
        literal_values = tuple(cast("list[Any]", values))
        value_types: set[type[Any]] = {type(value) for value in literal_values}
        if not value_types <= set(_LITERAL_VALUE_TYPES):
            raise _refuse(path=path, reason="the values of an enumeration are strings, integers or booleans")
        declared_type = node.get("type")
        if declared_type is not None and (len(value_types) != 1 or _LITERAL_VALUE_TYPES[value_types.pop()] != declared_type):
            raise _refuse(path=f"{path}/type", reason="the declared type is not the type of the values")
        return literal_values

    def _string(self, *, node: dict[str, Any], path: str) -> Any:
        _refuse_unknown_keys(node=node, allowed=_STRING_KEYS, path=path)
        string_format = node.get("format")
        if string_format is None:
            return self._constrained(base=str, node=node, keys=_STRING_KEYS, path=path)
        if string_format in _FORMAT_TYPES:
            _refuse_unknown_keys(node=node, allowed=frozenset({"type", "format"}), path=path)
            return _FORMAT_TYPES[string_format]
        if string_format == "uri":
            # pydantic writes a URL as a string of at least one character, and its length cap when it has one.
            _refuse_unknown_keys(node=node, allowed=frozenset({"type", "format", "minLength", "maxLength"}), path=path)
            if node.get("minLength") != 1:
                raise _refuse(path=f"{path}/minLength", reason="a URL is at least one character long")
            max_length = node.get("maxLength")
            if max_length is None:
                return AnyUrl
            if not _is_count(value=max_length):
                raise _refuse(path=f"{path}/maxLength", reason="a length is a count")
            return Annotated[AnyUrl, UrlConstraints(max_length=max_length)]
        raise _refuse(path=f"{path}/format", reason=f"the format {string_format!r} is not supported")

    def _constrained(self, *, base: Any, node: dict[str, Any], keys: frozenset[str], path: str) -> Any:
        _refuse_unknown_keys(node=node, allowed=keys, path=path)
        constraints: dict[str, Any] = {}
        for key, argument in _NUMERIC_CONSTRAINTS.items():
            if key in node:
                if not _is_number(value=node[key]):
                    raise _refuse(path=f"{path}/{key}", reason="a bound is a number")
                constraints[argument] = node[key]
        for key, argument in _LENGTH_CONSTRAINTS.items():
            if key in node:
                if not _is_count(value=node[key]):
                    raise _refuse(path=f"{path}/{key}", reason="a length is a count")
                constraints[argument] = node[key]
        if "pattern" in node:
            if not isinstance(node["pattern"], str):
                raise _refuse(path=f"{path}/pattern", reason="a pattern is a string")
            constraints["pattern"] = node["pattern"]
        if not constraints:
            return base
        return Annotated[base, Field(**constraints)]

    def _array(self, *, node: dict[str, Any], depth: int, path: str) -> Any:
        _refuse_unknown_keys(node=node, allowed=_ARRAY_KEYS, path=path)
        item_type = self._annotation(node=node["items"], depth=depth + 1, path=f"{path}/items") if "items" in node else Any
        unique_items = node.get("uniqueItems", False)
        if not isinstance(unique_items, bool):
            raise _refuse(path=f"{path}/uniqueItems", reason="uniqueItems is a boolean")
        # A type computed at runtime is subscripted through `GenericAlias`, which is what `list[...]` builds.
        container = GenericAlias(set if unique_items else list, (item_type,))
        constraints: dict[str, Any] = {}
        for key, argument in _ITEM_CONSTRAINTS.items():
            if key in node:
                if not _is_count(value=node[key]):
                    raise _refuse(path=f"{path}/{key}", reason="a length is a count")
                constraints[argument] = node[key]
        if not constraints:
            return container
        return Annotated[container, Field(**constraints)]

    def _dict(self, *, node: dict[str, Any], depth: int, path: str) -> Any:
        if "properties" in node:
            raise _refuse(path=path, reason="an inline object is not supported, only one in '$defs'")
        _refuse_unknown_keys(node=node, allowed=_DICT_KEYS, path=path)
        value_node = node.get("additionalProperties", True)
        if value_node is True:
            return dict[str, Any]
        value_type = self._annotation(node=value_node, depth=depth + 1, path=f"{path}/additionalProperties")
        return GenericAlias(dict, (str, value_type))

    def _reference(self, *, ref: Any, depth: int, path: str) -> Any:
        self._count_depth(depth=depth, path=path)
        if not isinstance(ref, str) or not ref.startswith(_LOCAL_REF_PREFIX):
            raise _refuse(path=path, reason=f"only a local '{_LOCAL_REF_PREFIX}…' reference is supported, not {ref!r}")
        def_name = ref.removeprefix(_LOCAL_REF_PREFIX)
        if def_name not in self._defs:
            raise _refuse(path=path, reason=f"it references '{def_name}', which '$defs' does not define")
        if def_name in self._built:
            return self._built[def_name]
        if def_name in self._in_progress:
            return ForwardRef(self._forward_refs[def_name])

        def_path = f"#/$defs/{def_name}"
        def_node = self._defs[def_name]
        built: Any
        if isinstance(def_node, dict) and "enum" in def_node:
            built = self._enum(node=cast("dict[str, Any]", def_node), def_name=def_name, path=def_path)
        else:
            self._forward_refs[def_name] = f"{_FORWARD_REF_PREFIX}{len(self._forward_refs)}"
            self._in_progress.add(def_name)
            built = self._model(node=def_node, fallback_name=def_name, depth=depth + 1, path=def_path)
            self._in_progress.discard(def_name)
            self._namespace[self._forward_refs[def_name]] = built
        self._built[def_name] = built
        return built

    def _enum(self, *, node: dict[str, Any], def_name: str, path: str) -> type[Enum]:
        _refuse_unknown_keys(node=node, allowed=_ENUM_DEF_KEYS, path=path)
        title = node.get("title", def_name)
        description = node.get("description")
        if not isinstance(title, str) or not title:
            raise _refuse(path=f"{path}/title", reason="the title is not a string")
        if description is not None and not isinstance(description, str):
            raise _refuse(path=f"{path}/description", reason="the description is not a string")
        values = self._literal_values(values=node["enum"], node=node, path=path)
        value_types: set[type[Any]] = {type(value) for value in values}
        if value_types not in ({str}, {int}):
            raise _refuse(path=path, reason="an enumeration class holds strings or integers")
        # The member names are not in the schema; the mixed-in value type keeps a member equal to its value.
        members = [(f"member_{index_value}", value) for index_value, value in enumerate(values)]
        enum_class = cast("type[Enum]", Enum(title, members, type=value_types.pop(), module="builtins"))
        enum_class.__doc__ = _doc_reading_back_as(description=description) if description else None
        return enum_class


def _empty_value() -> None:
    return None


def _empty_value_factory(*, annotation: Any) -> Callable[[], Any]:
    """The factory of a field's value when the schema says it is optional but shows no default."""
    container = annotation
    if get_origin(container) is Annotated:
        container = get_args(container)[0]
    empty_containers: dict[Any, Callable[[], Any]] = {list: list, set: set, dict: dict}
    return empty_containers.get(get_origin(container), _empty_value)


class SchemaToModelFactory:
    """Rebuild Pydantic BaseModel classes from JSON schemas; see the module docstring for the subset and the guards."""

    _SCHEMA_CACHE_MAX_SIZE: ClassVar[int] = 1024

    _schema_cache: ClassVar[OrderedDict[str, type[BaseModel]]] = OrderedDict()
    _cache_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def make_from_json_schema(cls, schema: dict[str, Any], *, class_name: str) -> type[BaseModel]:
        """Rebuild a BaseModel class from a JSON schema dict.

        Args:
            schema: The JSON schema as returned by SomeModel.model_json_schema().
            class_name: The class's name, used when the schema's root carries no title.

        Returns:
            A new BaseModel subclass whose `model_json_schema()` is `schema`.

        Raises:
            UnsupportedSchemaError: The schema leaves the supported subset or exceeds a guard.
        """
        _SchemaModelBuilder.check_size(schema=schema)
        cache_key = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()

        # Hold the lock for the entire call. This kills the same-schema thundering herd (N concurrent first misses
        # each paying a full rebuild) at the cost of also serializing cache hits on other schemas behind any in-flight
        # miss. That trade-off is acceptable because real workloads use a small bounded set of distinct schemas, each
        # rebuilt once and cached for the process lifetime, so post-warmup contention is limited to cache lookups.
        with cls._cache_lock:
            if cache_key in cls._schema_cache:
                cls._schema_cache.move_to_end(cache_key)
                return cls._schema_cache[cache_key]

            rebuilt_class = cls._build(schema=schema, class_name=class_name)
            if len(cls._schema_cache) >= cls._SCHEMA_CACHE_MAX_SIZE:
                cls._schema_cache.popitem(last=False)
            cls._schema_cache[cache_key] = rebuilt_class

        return rebuilt_class

    @classmethod
    def _build(cls, *, schema: dict[str, Any], class_name: str) -> type[BaseModel]:
        """Build the class of one schema the cache does not hold."""
        return _SchemaModelBuilder(schema=schema).build(schema=schema, class_name=class_name)
