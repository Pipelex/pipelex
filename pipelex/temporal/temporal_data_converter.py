"""This module was entirely rewritten based on Temporal's sample "pydantic_converter":
https://github.com/temporalio/samples-python/tree/main/pydantic_converter

The purpose of this converter is to serialize and deserialize inputs and outputs of Temporal activities and workflows.

Our implementation includes several key improvements:
- Compatibility with Pydantic v2
- Support for universal JSON serialization/deserialization via `pipelex.tools.serde.kajson`
- Preservation of subclass types

Please note that, while Temporal does not officially support Generics,
this converter serves as a reliable workaround for Pydantic models.
It also supports lists such as `List[BaseModel]` and `List[BaseModelSubclass]`.

For examples, see the tests in `test_top_crafter.py`:

1. `make ti TEST=test_make_object`
   - This test uses `WfCraftObject`, which returns a `BaseModel`.
   - However, the actual class of the returned object is determined by `object_assignment.object_class`,
     allowing the calling method to cast it to the required generic type with `cast(BaseModelType, obj)`.

2. `make ti TEST=test_make_object_list`
   - This test uses `WfCraftObjectList`, which returns a `List[BaseModel]`.
   - Similarly, the items in the returned list use the class specified in `object_assignment.object_class`,
     allowing the calling method to cast the list to the required generic type with `cast(List[BaseModelType], obj_list)`.
"""

from typing import Any, cast

from kajson import kajson
from kajson.class_registry import ClassRegistry
from pydantic import BaseModel
from pydantic.dataclasses import is_pydantic_dataclass
from temporalio.api.common.v1 import Payload
from temporalio.converter import (
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    EncodingPayloadConverter,
    JSONPlainPayloadConverter,
    PayloadCodec,
)
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.hub import get_class_registry


class BaseModelPayloadConverter(JSONPlainPayloadConverter):
    """Universal Pydantic JSON payload converter.

    This extends the :py:class:`JSONPlainPayloadConverter` to override :py:meth:`to_payload`.
    """

    @classmethod
    def _is_kajson_wire_value(cls, value: object) -> bool:
        """A value kajson serializes with type preservation: a BaseModel instance or a pydantic dataclass instance.

        The BaseModel check is first so it short-circuits on the hot path before the pydantic-dataclass probe.
        """
        return isinstance(value, BaseModel) or is_pydantic_dataclass(type(value))

    def _kajson_to_payload(self, value: object, *, source_type_holder: object) -> Payload:
        """Serialize a kajson wire value (or list of them) to a Payload.

        ``source_type_holder`` is the object whose type may carry a dynamic-class ``__kajson_class_source__``
        (the value itself for a scalar, or the first element for a list). That attribute is absent on pydantic
        dataclasses — only dynamically-built BaseModel classes set it — so the lookup is harmlessly ``None`` there.
        """
        payload_str: str = kajson.dumps(value)
        metadata: dict[str, bytes] = {"encoding": self.encoding.encode()}
        class_source = getattr(type(source_type_holder), "__kajson_class_source__", None)
        if class_source is not None:
            metadata["kajson_class_source"] = class_source.encode()
        return Payload(metadata=metadata, data=payload_str.encode())

    @classmethod
    def _first_kajson_list_element(cls, value: object) -> object | None:
        """Return the first element if value is a non-empty list whose head is a kajson wire value, else None."""
        if not isinstance(value, list):
            return None
        items = cast("list[object]", value)
        if items and cls._is_kajson_wire_value(items[0]):
            return items[0]
        return None

    @override
    def to_payload(self, value: Any) -> Payload | None:
        if self._is_kajson_wire_value(value):
            return self._kajson_to_payload(value, source_type_holder=value)
        list_head = self._first_kajson_list_element(value)
        if list_head is not None:
            return self._kajson_to_payload(value, source_type_holder=list_head)
        return super().to_payload(value)

    def _restore_class_source(self, value: BaseModel, *, class_source_code: str) -> None:
        value_class = cast("Any", type(value))
        value_class.__kajson_class_source__ = class_source_code

    def _kajson_deserialize_from_payload(self, payload: Payload) -> Any:
        data = payload.data.decode()
        log.verbose(f"unijson_deserialize_payload — data: {data}")
        source_bytes = payload.metadata.get("kajson_class_source")
        class_source_code = source_bytes.decode() if source_bytes else None

        global_registry = get_class_registry()
        if class_source_code is not None:
            # Build a per-call scoped registry overlaying the global one with the
            # source-derived dynamic classes (BaseModel + Enum). Per-call so dynamic
            # classes never persist across payloads — different schemas may reuse the
            # same class name without collision.
            source_types = SchemaToModelFactory.make_types_from_source(class_source_code)
            scoped_registry = ClassRegistry()
            scoped_registry.register_classes_dict(global_registry.get_classes_dict())
            for type_name, type_obj in source_types.items():
                scoped_registry.register_class(type_obj, name=type_name, should_warn_if_already_registered=False)
            pydantic_gizmo = kajson.loads(data, class_registry=scoped_registry)
        else:
            pydantic_gizmo = kajson.loads(data, class_registry=global_registry)

        if class_source_code is not None:
            if isinstance(pydantic_gizmo, BaseModel):
                self._restore_class_source(pydantic_gizmo, class_source_code=class_source_code)
            elif isinstance(pydantic_gizmo, list):
                for item in cast("list[Any]", pydantic_gizmo):
                    if isinstance(item, BaseModel):
                        self._restore_class_source(item, class_source_code=class_source_code)
        log.verbose(f"unijson_deserialize_payload — pydantic_gizmo: {pydantic_gizmo}")
        return cast("Any", pydantic_gizmo)

    @classmethod
    def _is_kajson_type(cls, type_hint: Any) -> bool:
        """A type kajson reconstructs with type preservation: a BaseModel subclass or a pydantic dataclass.

        The inner args of ``Optional`` / ``list`` hints may be typing constructs rather than classes;
        ``is_pydantic_dataclass`` returns ``False`` for those without raising, so no guard is needed.
        """
        if isinstance(type_hint, type) and issubclass(type_hint, BaseModel):
            return True
        # cast collapses the post-isinstance ``Any | type[Unknown]`` back to ``Any`` for the typed probe.
        return is_pydantic_dataclass(cast("Any", type_hint))

    @classmethod
    def _unwrap_optional_kajson_type(cls, type_hint: type[Any] | None) -> bool:
        """Check if type_hint is Optional[X] / X | None where X is a kajson wire type."""
        if type_hint is None:
            return False
        args = getattr(type_hint, "__args__", None)
        if args is None:
            return False
        # Optional[X] is Union[X, None] — check if any non-None arg is a kajson wire type
        for arg in args:
            if arg is type(None):
                continue
            if cls._is_kajson_type(arg):
                return True
        return False

    @override
    def from_payload(
        self,
        payload: Payload,
        type_hint: type[Any] | None = None,
    ) -> Any:
        # BaseModel / pydantic-dataclass scalar case
        if self._is_kajson_type(type_hint):
            return self._kajson_deserialize_from_payload(payload=payload)

        # Optional case (e.g. GraphSpec | None)
        if self._unwrap_optional_kajson_type(type_hint):
            return self._kajson_deserialize_from_payload(payload=payload)

        # list case
        origin = getattr(type_hint, "__origin__", None)
        args = getattr(type_hint, "__args__", None)
        log.verbose(f"Type hint origin: {origin}, args: {args}")
        if origin is list and args and len(args) == 1 and self._is_kajson_type(args[0]):
            log.debug(f"Type hint is a list of kajson wire type: {args[0]}")
            return self._kajson_deserialize_from_payload(payload=payload)

        log.verbose(f"The type hint '{type_hint}' is neither a kajson wire type nor a list of kajson wire types")
        return super().from_payload(payload, type_hint)  # pyright: ignore[reportUnknownMemberType]


class PydanticCompositePayloadConverter(CompositePayloadConverter):
    """Payload converter that replaces Temporal JSON conversion without BaseModelPayloadConverter JSON conversion."""

    def __init__(self) -> None:
        converters: list[EncodingPayloadConverter] = []
        for converter in DefaultPayloadConverter.default_encoding_payload_converters:
            if isinstance(converter, JSONPlainPayloadConverter):
                converters.append(BaseModelPayloadConverter())
            else:
                converters.append(converter)

        super().__init__(*converters)


def make_data_converter(payload_codec: PayloadCodec | None = None) -> DataConverter:
    """Create a DataConverter with our Pydantic-aware payload converter and an optional codec.

    Args:
        payload_codec: Optional codec for offloading large payloads to external storage.
    """
    return DataConverter(
        payload_converter_class=PydanticCompositePayloadConverter,
        payload_codec=payload_codec,
    )


data_converter = make_data_converter()
