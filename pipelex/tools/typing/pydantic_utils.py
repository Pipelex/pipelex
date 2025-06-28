from typing import Any, Dict, List, Optional, Sequence, Set, TypeVar, Union

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


def convert_strenum_to_str(
    obj: Dict[str, Any] | List[Any] | StrEnum | Any,
) -> Dict[str, Any] | List[Any] | str | Any:
    if isinstance(obj, dict):
        obj_dict: Dict[str, Any] = obj
        return {str(key): convert_strenum_to_str(value) for key, value in obj_dict.items()}
    elif isinstance(obj, list):
        obj_list: List[Any] = obj
        return [convert_strenum_to_str(item) for item in obj_list]
    elif isinstance(obj, StrEnum):
        if hasattr(obj, "display_name"):
            return obj.display_name()  # type: ignore
        return str(obj)
    else:
        return obj


class ExtraFieldAttribute(StrEnum):
    IS_HIDDEN = "is_hidden"


class FieldVisibility(StrEnum):
    ALL_FIELDS = "all_fields"
    NO_HIDDEN_FIELDS = "no_hidden_fields"
    ONLY_HIDDEN_FIELDS = "only_hidden_fields"


def clean_model_to_dict(obj: BaseModel) -> Dict[str, Any]:
    dict_dump = serialize_model(
        obj=obj,
        field_visibility=FieldVisibility.NO_HIDDEN_FIELDS,
        is_stringify_enums=True,
    )
    if not isinstance(dict_dump, dict):
        raise TypeError(f"Expected dict, got {type(dict_dump)}")
    result_dict: Dict[str, Any] = dict_dump
    return result_dict


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
        json_schema_extra = field_info.json_schema_extra
        is_hidden = json_schema_extra and isinstance(json_schema_extra, dict) and json_schema_extra.get(ExtraFieldAttribute.IS_HIDDEN) is True
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
            value_list: List[Any] = value
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
            value_dict: Dict[str, Any] = value
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


class CustomBaseModel(BaseModel):
    @override
    def __rich_repr__(self) -> RichReprResult:  # type: ignore
        for item in super().__rich_repr__():  # type: ignore
            if isinstance(item, tuple):
                tuple_item: tuple[Any, ...] = item
                if len(tuple_item) >= 2:
                    name = tuple_item[0]
                    value = tuple_item[1]
                    if AttributePolisher.should_truncate(name=name, value=value):
                        truncated_value = AttributePolisher.get_truncated_value(name, value)
                        if len(tuple_item) == 3:
                            yield name, truncated_value, tuple_item[2]
                        else:
                            yield name, truncated_value
                    else:
                        yield item
            else:
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

        # If it's a dictionary, recurse into its values
        if isinstance(obj, dict):
            obj_dict: Dict[str, Any] = obj
            truncated_dict: Dict[str, Any] = {}
            for key, value in obj_dict.items():
                truncated_dict[key] = self._apply_truncation_recursive(value, name=key)
            return truncated_dict

        # If it's a list, recurse into its items
        elif isinstance(obj, list):
            obj_list: List[Any] = obj
            return [self._apply_truncation_recursive(item, name=name) for item in obj_list]

        # If it's a tuple, recurse into its items and return as tuple
        elif isinstance(obj, tuple):
            return tuple(self._apply_truncation_recursive(item, name=name) for item in obj)  # type: ignore

        # For all other types, return as-is
        else:
            return obj
