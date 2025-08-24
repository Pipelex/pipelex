import json
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, TypeGuard, TypeVar, Union, cast, overload

from pydantic import BaseModel, ValidationError
from rich.repr import Result as RichReprResult
from typing_extensions import override

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.types import StrEnum

BaseModelTypeVar = TypeVar("BaseModelTypeVar", bound=BaseModel)


def format_pydantic_validation_error(exc: ValidationError) -> str:
    """Format a Pydantic ValidationError into a readable string with detailed error information.

    Args:
        exc: The Pydantic ValidationError exception

    Returns:
        A formatted string containing categorized validation errors
    """
    error_msg = "Validation error(s):"

    # Collect different types of validation errors
    missing_fields = [f"{'.'.join(map(str, err['loc']))}" for err in exc.errors() if err["type"] == "missing"]
    extra_fields = [f"{'.'.join(map(str, err['loc']))}: {err['input']}" for err in exc.errors() if err["type"] == "extra_forbidden"]
    type_errors = [f"{'.'.join(map(str, err['loc']))}: expected {err['type']}" for err in exc.errors() if err["type"] == "type_error"]
    value_errors = [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors() if err["type"] == "value_error"]
    enum_errors = [
        f"{'.'.join(map(str, err['loc']))}: invalid enum value '{err.get('input', 'unknown')}'" for err in exc.errors() if err["type"] == "enum"
    ]
    model_type_errors: List[str] = []
    for err in exc.errors():
        if err["type"] == "model_type":
            field_path = ".".join(map(str, err["loc"]))
            # Extract expected type from context if available
            expected_type = err.get("ctx", {}).get("class_name", "unknown model type")
            actual_input = err.get("input", "unknown")
            actual_type = type(actual_input).__name__ if actual_input != "unknown" else "unknown"
            model_type_errors.append(f"{field_path}: expected {expected_type}, got {actual_type}")

    # Add each type of error to the message if present
    if missing_fields:
        error_msg += f"\nMissing required fields: {missing_fields}"
    if extra_fields:
        error_msg += f"\nExtra forbidden fields: {extra_fields}"
    if type_errors:
        error_msg += f"\nType errors: {type_errors}"
    if value_errors:
        error_msg += f"\nValue errors: {value_errors}"
    if enum_errors:
        error_msg += f"\nEnum errors: {enum_errors}"
    if model_type_errors:
        error_msg += f"\nModel type errors: {model_type_errors}"

    # If none of the specific error types were found, add the raw error messages
    if not any([missing_fields, extra_fields, type_errors, value_errors, enum_errors, model_type_errors]):
        error_msg += "\nOther validation errors:"
        for err in exc.errors():
            error_msg += f"\n{'.'.join(map(str, err['loc']))}: {err['type']}: {err['msg']}"

    return error_msg


@overload
def convert_strenum_to_str(obj: dict[str, Any]) -> dict[str, Any]: ...
@overload
def convert_strenum_to_str(obj: list[Any]) -> list[Any]: ...
@overload
def convert_strenum_to_str(obj: StrEnum) -> str: ...
@overload
def convert_strenum_to_str(obj: object) -> object: ...


def convert_strenum_to_str(obj: object) -> object:
    if isinstance(obj, dict):
        obj_dict = cast(dict[str, Any], obj)
        out: dict[str, Any] = {}
        for k, v in obj_dict.items():
            out[str(k)] = cast(Any, convert_strenum_to_str(v))  # keep values as Any
        return out

    if isinstance(obj, list):
        obj_list = cast(list[Any], obj)
        return [cast(Any, convert_strenum_to_str(item)) for item in obj_list]

    if isinstance(obj, StrEnum):
        dn = getattr(obj, "display_name", None)
        if callable(dn):
            return cast(str, dn())
        return str(obj)

    return obj


class ExtraFieldAttribute(StrEnum):
    IS_HIDDEN = "is_hidden"


class FieldVisibility(StrEnum):
    ALL_FIELDS = "all_fields"
    NO_HIDDEN_FIELDS = "no_hidden_fields"
    ONLY_HIDDEN_FIELDS = "only_hidden_fields"


def clean_model_to_dict(obj: BaseModel) -> dict[str, Any]:
    dict_dump = serialize_model(
        obj=obj,
        field_visibility=FieldVisibility.NO_HIDDEN_FIELDS,
        is_stringify_enums=True,
    )
    return dict_dump


def clean_model_to_string(obj: BaseModel) -> str:
    """Convert a BaseModel to a clean JSON string representation.

    Args:
        obj: The Pydantic BaseModel to convert

    Returns:
        A JSON string representation of the model with hidden fields omitted
        and enums stringified
    """
    dict_dump = clean_model_to_dict(obj)
    return json.dumps(dict_dump, indent=2, ensure_ascii=False)


@overload
def serialize_model(
    obj: BaseModel,
    field_visibility: FieldVisibility = FieldVisibility.NO_HIDDEN_FIELDS,
    is_stringify_enums: bool = True,
) -> dict[str, Any]: ...
@overload
def serialize_model(
    obj: list[Any],
    field_visibility: FieldVisibility = FieldVisibility.NO_HIDDEN_FIELDS,
    is_stringify_enums: bool = True,
) -> list[Any]: ...
@overload
def serialize_model(
    obj: dict[str, Any],
    field_visibility: FieldVisibility = FieldVisibility.NO_HIDDEN_FIELDS,
    is_stringify_enums: bool = True,
) -> dict[str, Any]: ...
@overload
def serialize_model(
    obj: object,
    field_visibility: FieldVisibility = FieldVisibility.NO_HIDDEN_FIELDS,
    is_stringify_enums: bool = True,
) -> Any: ...


def serialize_model(
    obj: Any,
    field_visibility: FieldVisibility = FieldVisibility.NO_HIDDEN_FIELDS,
    is_stringify_enums: bool = True,
) -> Union[Dict[str, Any], List[Any], Any]:
    """
    Recursively serialize a Pydantic BaseModel (and its nested BaseModels)
    into a dictionary, omitting any fields marked with
    'json_schema_extra={ExtraFieldAttribute.IS_HIDDEN: True}'.

    If 'obj' is not a BaseModel, return it as-is (useful for nested lists/dicts).
    """
    # If it's not a Pydantic model, return it directly
    if not isinstance(obj, BaseModel):
        # Might be a primitive type, list, dict, etc.
        # We only handle nesting if it's inside BaseModels
        return obj

    # Identify which fields should be excluded
    fields_to_exclude: Set[str] = set()

    for field_name, field_info in obj.__class__.model_fields.items():
        extra = field_info.json_schema_extra

        is_hidden = False
        if isinstance(extra, Mapping):  # narrow first
            extra_map = cast(Mapping[str, Any], extra)  # give key/value types
            is_hidden = bool(extra_map.get(ExtraFieldAttribute.IS_HIDDEN.value, False))
        match field_visibility:
            case FieldVisibility.ALL_FIELDS:
                pass
            case FieldVisibility.NO_HIDDEN_FIELDS:
                if is_hidden:
                    fields_to_exclude.add(field_name)
            case FieldVisibility.ONLY_HIDDEN_FIELDS:
                if not is_hidden:
                    fields_to_exclude.add(field_name)

    # Build a dict, omitting hidden fields. Recursively handle nested models.
    data: Dict[str, Any] = {}
    for field_name, _ in obj.__class__.model_fields.items():
        if field_name in fields_to_exclude:
            continue  # Skip hidden fields

        value = getattr(obj, field_name)

        # If the value is another BaseModel, recurse
        if isinstance(value, BaseModel):
            data[field_name] = serialize_model(
                obj=value,
                field_visibility=field_visibility,
                is_stringify_enums=is_stringify_enums,
            )

        # If it's a list, we recurse for each item
        elif isinstance(value, list):
            value_list = cast(List[Any], value)
            data[field_name] = [
                serialize_model(
                    obj=item,
                    field_visibility=field_visibility,
                    is_stringify_enums=is_stringify_enums,
                )
                for item in value_list
            ]

        # If it's a dict, we can similarly recurse for any nested BaseModels inside the dict
        elif isinstance(value, dict):
            value_dict = cast(Dict[str, Any], value)
            data[field_name] = {
                key: serialize_model(
                    obj=value,
                    field_visibility=field_visibility,
                    is_stringify_enums=is_stringify_enums,
                )
                for key, value in value_dict.items()
            }

        elif is_stringify_enums and isinstance(value, StrEnum):
            if hasattr(value, "display_name"):
                data[field_name] = value.display_name()  # type: ignore
            else:
                data[field_name] = str(value)

        # Otherwise, just store the raw value
        else:
            data[field_name] = value

    return data


def _is_name_value(t: tuple[object, ...]) -> TypeGuard[tuple[str, Any]]:
    return len(t) == 2 and isinstance(t[0], str)


def _is_name_value_hint(t: tuple[object, ...]) -> TypeGuard[tuple[str, Any, Any]]:
    return len(t) == 3 and isinstance(t[0], str)


class CustomBaseModel(BaseModel):
    @override
    def __rich_repr__(self) -> RichReprResult:
        parent = getattr(super(CustomBaseModel, self), "__rich_repr__", None)

        items: RichReprResult
        if callable(parent):
            items = cast(RichReprResult, parent())
        else:
            items = cast(RichReprResult, ())

        for item in items:
            if isinstance(item, tuple):
                typed_item: tuple[object, ...] = cast(tuple[object, ...], item)

                if _is_name_value(typed_item):
                    name, value = typed_item
                    if AttributePolisher.should_truncate(name=name, value=value):
                        yield name, AttributePolisher.get_truncated_value(name, value)
                        continue

                elif _is_name_value_hint(typed_item):
                    name, value, hint = typed_item
                    if AttributePolisher.should_truncate(name=name, value=value):
                        yield name, AttributePolisher.get_truncated_value(name, value), hint
                        continue

            yield item

    @override
    def __repr_args__(self) -> Sequence[tuple[Optional[str], Any]]:
        processed_args: list[tuple[Optional[str], Any]] = []
        for name, value in super().__repr_args__():
            if name and AttributePolisher.should_truncate(name=name, value=value):
                truncated_value = AttributePolisher.get_truncated_value(name, value)
                processed_args.append((name, truncated_value))
            else:
                processed_args.append((name, value))
        return processed_args

    def model_dump_truncated(self, **kwargs: Any) -> Any:
        """
        Dump the model to a dictionary with serialize_as_any=True and apply
        AttributePolisher truncation to fields that should be truncated.
        Handles nested attributes recursively.

        Args:
            **kwargs: Additional keyword arguments to pass to model_dump

        Returns:
            Dictionary with truncated values where appropriate
        """
        # Get the model dump with serialize_as_any=True
        dumped_data = self.model_dump(**kwargs)

        # Apply truncation logic recursively
        return self._apply_truncation_recursive(dumped_data)

    def _apply_truncation_recursive(self, obj: Any, name: Optional[str] = None) -> Any:
        """
        Recursively apply AttributePolisher truncation logic to a data structure.

        Args:
            obj: The object to process
            name: The field name (for truncation logic)

        Returns:
            The processed object with truncation applied where appropriate
        """
        # First check if this specific object should be truncated
        if name and AttributePolisher.should_truncate(name=name, value=obj):
            return AttributePolisher.get_truncated_value(name, obj)

        if isinstance(obj, dict):
            obj_dict = cast(Dict[str, Any], obj)
            truncated_dict: Dict[str, Any] = {}
            for key, value in obj_dict.items():
                truncated_dict[key] = self._apply_truncation_recursive(value, name=key)
            return truncated_dict

        elif isinstance(obj, list):
            obj_list = cast(List[Any], obj)
            return [self._apply_truncation_recursive(item, name=name) for item in obj_list]

        elif isinstance(obj, tuple):
            cast_obj = cast(Tuple[Any, ...], obj)
            return tuple(self._apply_truncation_recursive(item, name=name) for item in cast_obj)

        else:
            return obj
