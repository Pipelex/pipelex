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

1. `make ti TEST=test_make_object_direct`
   - This test uses `WfCraftObject`, which returns a `BaseModel`.
   - However, the actual class of the returned object is determined by `object_assignment.object_class`,
     allowing the calling method to cast it to the required generic type with `cast(BaseModelType, obj)`.

2. `make ti TEST=test_make_object_list_direct`
   - This test uses `WfCraftObjectList`, which returns a `List[BaseModel]`.
   - Similarly, the items in the returned list use the class specified in `object_assignment.object_class`,
     allowing the calling method to cast the list to the required generic type with `cast(List[BaseModelType], obj_list)`.
"""

from typing import Any

from kajson import kajson
from pydantic import BaseModel
from temporalio.api.common.v1 import Payload
from temporalio.converter import (
    CompositePayloadConverter,
    DataConverter,
    DefaultPayloadConverter,
    EncodingPayloadConverter,
    JSONPlainPayloadConverter,
)
from typing_extensions import override

from pipelex import log
from pipelex.deep_flow.exceptions import DeepFlowError


class BaseModelPayloadConverterError(DeepFlowError):
    pass


class BaseModelPayloadConverter(JSONPlainPayloadConverter):
    """Universal Pydantic JSON payload converter.

    This extends the :py:class:`JSONPlainPayloadConverter` to override :py:meth:`to_payload`.
    """

    def _unijson_serialize_to_payload(self, value: Any) -> Payload:
        payload_str: str = kajson.dumps(value)
        return Payload(
            metadata={"encoding": self.encoding.encode()},
            data=payload_str.encode(),
        )

    @override
    def to_payload(self, value: Any) -> Payload | None:
        if isinstance(value, BaseModel):
            payload_str: str = kajson.dumps(value)
            return Payload(
                metadata={"encoding": self.encoding.encode()},
                data=payload_str.encode(),
            )
        elif isinstance(value, list) and value and isinstance(value[0], BaseModel):
            list_payload_str: str = kajson.dumps(value)
            return Payload(
                metadata={"encoding": self.encoding.encode()},
                data=list_payload_str.encode(),
            )
        else:
            return super().to_payload(value)

    def _kajson_deserialize_from_payload(self, payload: Payload) -> Any:
        data = payload.data.decode()
        log.verbose(f"unijson_deserialize_payload — data: {data}")
        pydantic_gizmo = kajson.loads(data)
        log.verbose(f"unijson_deserialize_payload — pydantic_gizmo: {pydantic_gizmo}")
        return pydantic_gizmo

    @override
    def from_payload(
        self,
        payload: Payload,
        type_hint: type[Any] | None = None,
    ) -> Any:
        # BaseModel case
        if isinstance(type_hint, type) and issubclass(type_hint, BaseModel):  # pyright: ignore[reportUnnecessaryIsInstance]
            return self._kajson_deserialize_from_payload(payload=payload)

        # BaseModel list case
        origin = getattr(type_hint, "__origin__", None)
        args = getattr(type_hint, "__args__", None)
        log.verbose(f"Type hint origin: {origin}, args: {args}")
        if origin is list and args and len(args) == 1 and issubclass(args[0], BaseModel):
            log.debug(f"Type hint is a List of BaseModel: {args[0]}")
            return self._kajson_deserialize_from_payload(payload=payload)

        log.verbose(f"The type hint '{type_hint}' is neither a subclass of BaseModel nor a List of BaseModel")
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


data_converter = DataConverter(payload_converter_class=PydanticCompositePayloadConverter)
