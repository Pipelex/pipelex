from __future__ import annotations

import json as json_module
from typing import TYPE_CHECKING, Any, TypeVar, cast

from pydantic import BaseModel, ValidationError
from typing_extensions import override

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from rich.repr import Result as RichReprResult

BaseModelTypeVar = TypeVar("BaseModelTypeVar", bound=BaseModel)

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


def empty_list_factory_of(_: type[T]) -> Callable[[], list[T]]:
    def _factory() -> list[T]:
        return []

    return _factory


def empty_dict_factory_of(_key: type[K], _val: type[V] | None = None) -> Callable[[], dict[K, Any]]:
    """Create a typed empty dict factory.

    Args:
        _key: The key type (used for type inference)
        _val: The value type (optional, used for type inference)

    Returns:
        A callable that returns an empty dict

    """

    def _factory() -> dict[K, Any]:
        return {}

    return _factory


class PydanticValidationErrorAnalysis(BaseModel):
    error_msg: str

    missing_fields: list[str]
    extra_fields: list[str]
    type_errors: list[str]
    value_errors: list[str]
    enum_errors: list[str]
    literal_errors: list[str]
    union_tag_errors: list[str]
    model_type_errors: list[str]


def analyze_pydantic_validation_error(exc: ValidationError) -> PydanticValidationErrorAnalysis:
    """Analyze a Pydantic ValidationError into a readable string with detailed error information.

    Args:
        exc: The Pydantic ValidationError exception

    Returns:
        A PydanticValidationErrorAnalysis object containing categorized validation errors

    """
    error_msg = "Validation error(s):"

    # Collect different types of validation errors
    missing_fields = [f"'{'.'.join(map(str, err['loc']))}'" for err in exc.errors() if err["type"] == "missing"]
    extra_fields = [f"'{'.'.join(map(str, err['loc']))}'" for err in exc.errors() if err["type"] == "extra_forbidden"]
    type_errors = [f"'{'.'.join(map(str, err['loc']))}': expected {err['type']}" for err in exc.errors() if err["type"] == "type_error"]
    value_errors = [f"'{'.'.join(map(str, err['loc']))}': {err['msg']}" for err in exc.errors() if err["type"] == "value_error"]
    enum_errors = [
        f"'{'.'.join(map(str, err['loc']))}': invalid enum value '{err.get('input', 'unknown')}'" for err in exc.errors() if err["type"] == "enum"
    ]
    literal_errors: list[str] = []
    for err in exc.errors():
        if err["type"] == "literal_error":
            field_path = ".".join(map(str, err["loc"]))
            actual_input = err.get("input", "unknown")
            expected = err.get("ctx", {}).get("expected", "unknown")
            literal_errors.append(f"'{field_path}': got '{actual_input}', expected one of {expected}")

    union_tag_errors: list[str] = []
    for err in exc.errors():
        if err["type"] == "union_tag_not_found":
            field_path = ".".join(map(str, err["loc"]))
            # Extract discriminator field name from context
            discriminator = err.get("ctx", {}).get("discriminator", "type")
            union_tag_errors.append(f"'{field_path}': missing required discriminator field '{discriminator}'")

    model_type_errors: list[str] = []
    for err in exc.errors():
        if err["type"] == "model_type":
            field_path = ".".join(map(str, err["loc"]))
            # Extract expected type from context if available
            expected_type = err.get("ctx", {}).get("class_name", "unknown model type")
            actual_input = err.get("input", "unknown")
            actual_type = type(actual_input).__name__ if actual_input != "unknown" else "unknown"
            model_type_errors.append(f"'{field_path}': expected {expected_type}, got {actual_type}")

    # Add each type of error to the message if present
    if missing_fields:
        error_msg += f"\n\nMissing required fields: {', '.join(missing_fields)}"
    if extra_fields:
        error_msg += f"\n\nExtra forbidden fields: {', '.join(extra_fields)}"
    if type_errors:
        error_msg += f"\n\nType errors: {', '.join(type_errors)}"
    if value_errors:
        error_msg += f"\n\nValue errors: {', '.join(value_errors)}"
    if enum_errors:
        error_msg += f"\n\nEnum errors: {', '.join(enum_errors)}"
    if literal_errors:
        error_msg += f"\n\nInvalid choice errors: {', '.join(literal_errors)}"
    if union_tag_errors:
        error_msg += f"\n\nUnion discriminator errors: {', '.join(union_tag_errors)}"
    if model_type_errors:
        error_msg += f"\n\nModel type errors: {', '.join(model_type_errors)}"

    # If none of the specific error types were found, add the raw error messages
    if not any([missing_fields, extra_fields, type_errors, value_errors, enum_errors, literal_errors, union_tag_errors, model_type_errors]):
        error_msg += "\n\nOther validation errors:"
        for err in exc.errors():
            error_msg += f"\n{'.'.join(map(str, err['loc']))}: {err['type']}: {err['msg']}"

    return PydanticValidationErrorAnalysis(
        error_msg=error_msg,
        missing_fields=missing_fields,
        extra_fields=extra_fields,
        type_errors=type_errors,
        value_errors=value_errors,
        enum_errors=enum_errors,
        literal_errors=literal_errors,
        union_tag_errors=union_tag_errors,
        model_type_errors=model_type_errors,
    )


def format_pydantic_validation_error(exc: ValidationError) -> str:
    """Format a Pydantic ValidationError into a readable string with detailed error information.

    Args:
        exc: The Pydantic ValidationError exception

    Returns:
        A formatted string containing categorized validation errors

    """
    return analyze_pydantic_validation_error(exc).error_msg


def _serialize_input_value(value: Any) -> Any:
    """Serialize an input value for JSON output, falling back to repr() for non-serializable objects.

    Args:
        value: The input value from a pydantic validation error.

    Returns:
        A JSON-serializable representation of the value.

    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (dict, list)):
        typed_value: dict[str, Any] | list[Any] = cast("dict[str, Any] | list[Any]", value)
        try:
            json_module.dumps(typed_value)
            return typed_value
        except (TypeError, ValueError):
            return repr(typed_value)
    return repr(value)


def _serialize_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Serialize a pydantic error context dict so every value is JSON-safe.

    Pydantic context dicts can contain non-JSON-serializable objects (type objects,
    enum instances, etc.). This applies _serialize_input_value() to each value.

    Args:
        ctx: The context dict from a pydantic validation error.

    Returns:
        A dict with all values guaranteed to be JSON-serializable.

    """
    return {key: _serialize_input_value(value) for key, value in ctx.items()}


def format_pydantic_validation_error_for_agent(exc: ValidationError) -> tuple[str, dict[str, Any]]:
    """Format a Pydantic ValidationError into a concise message and structured details dict for agent CLI output.

    Args:
        exc: The Pydantic ValidationError exception

    Returns:
        A tuple of (message, details) where message is a concise summary string
        and details is a structured dict with model name, error count, categories, and per-error info.

    """
    analysis = analyze_pydantic_validation_error(exc)
    model_name = exc.title
    error_count = exc.error_count()

    # Build categories dict with only non-empty lists
    all_categories: dict[str, list[str]] = {
        "missing_fields": analysis.missing_fields,
        "extra_fields": analysis.extra_fields,
        "type_errors": analysis.type_errors,
        "value_errors": analysis.value_errors,
        "enum_errors": analysis.enum_errors,
        "literal_errors": analysis.literal_errors,
        "union_tag_errors": analysis.union_tag_errors,
        "model_type_errors": analysis.model_type_errors,
    }
    categories = {key: value for key, value in all_categories.items() if value}

    # Build per-error details list
    errors: list[dict[str, Any]] = []
    for err in exc.errors():
        field_path = ".".join(map(str, err["loc"])) if err["loc"] else ""
        error_detail: dict[str, Any] = {
            "field_path": field_path,
            "error_type": err["type"],
            "message": err["msg"],
            "input_value": _serialize_input_value(err.get("input")),
            "context": _serialize_context(err.get("ctx", {})),
        }
        errors.append(error_detail)

    # Build concise summary message
    category_summaries: list[str] = []
    if analysis.missing_fields:
        field_names = ", ".join(f.strip("'") for f in analysis.missing_fields)
        category_summaries.append(
            f"missing required fields: '{field_names}'"
            if len(analysis.missing_fields) == 1
            else f"missing required fields: {', '.join(analysis.missing_fields)}"
        )
    if analysis.extra_fields:
        category_summaries.append(f"extra forbidden fields: {', '.join(analysis.extra_fields)}")
    if analysis.type_errors:
        category_summaries.append(f"type errors: {', '.join(analysis.type_errors)}")
    if analysis.value_errors:
        category_summaries.append(f"value errors: {', '.join(analysis.value_errors)}")
    if analysis.enum_errors:
        category_summaries.append(f"enum errors: {', '.join(analysis.enum_errors)}")
    if analysis.literal_errors:
        category_summaries.append(f"literal errors: {', '.join(analysis.literal_errors)}")
    if analysis.union_tag_errors:
        category_summaries.append(f"union tag errors: {', '.join(analysis.union_tag_errors)}")
    if analysis.model_type_errors:
        category_summaries.append(f"model type errors: {', '.join(analysis.model_type_errors)}")

    error_word = "error" if error_count == 1 else "errors"
    if category_summaries:
        message = f"Validation failed for {model_name}: {error_count} {error_word} ({'; '.join(category_summaries)})"
    else:
        message = f"Validation failed for {model_name}: {error_count} {error_word}"

    details: dict[str, Any] = {
        "model": model_name,
        "error_count": error_count,
        "categories": categories,
        "errors": errors,
    }

    return message, details


def convert_strenum_to_str(
    obj: dict[str, Any] | list[Any] | StrEnum | Any,
) -> dict[str, Any] | list[Any] | str | Any:
    if isinstance(obj, dict):
        obj_dict = cast("dict[str, Any]", obj)
        return {str(key): convert_strenum_to_str(value) for key, value in obj_dict.items()}
    elif isinstance(obj, list):
        obj_list = cast("list[Any]", obj)
        return [convert_strenum_to_str(item) for item in obj_list]
    elif isinstance(obj, StrEnum):
        if hasattr(obj, "display_name"):
            return obj.display_name()  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportAttributeAccessIssue]
        else:
            return str(obj)
    else:
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
    if not isinstance(dict_dump, dict):
        msg = f"Expected dict, got {type(dict_dump)}"
        raise TypeError(msg)
    return cast("dict[str, Any]", dict_dump)


def serialize_model(
    obj: Any,
    field_visibility: FieldVisibility = FieldVisibility.NO_HIDDEN_FIELDS,
    is_stringify_enums: bool = True,
) -> dict[str, Any] | list[Any] | Any:
    """Recursively serialize a Pydantic BaseModel (and its nested BaseModels)
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
    fields_to_exclude: set[str] = set()

    for field_name, field_info in obj.__class__.model_fields.items():
        json_schema_extra = field_info.json_schema_extra
        is_hidden: bool
        if json_schema_extra and isinstance(json_schema_extra, dict):
            typed_json_schema_extra = cast("dict[str, Any]", json_schema_extra)
            is_hidden = typed_json_schema_extra.get(ExtraFieldAttribute.IS_HIDDEN) is True
        else:
            is_hidden = False
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
    data: dict[str, Any] = {}
    for field_name in obj.__class__.model_fields:
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
            value_list = cast("list[Any]", value)
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
            value_dict = cast("dict[str, Any]", value)
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
                data[field_name] = value.display_name()  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            else:
                data[field_name] = str(value)

        # Otherwise, just store the raw value
        else:
            data[field_name] = value

    return data


def _truncated_rich_repr_from_items(rich_repr_items: RichReprResult) -> RichReprResult:
    """Apply truncation to rich repr items.

    This applies AttributePolisher truncation to field values recursively,
    handling nested dicts, lists, and BaseModel objects.
    """
    for item in rich_repr_items:
        if isinstance(item, tuple):
            tuple_item = cast("tuple[Any, ...]", item)
            if len(tuple_item) >= 2:
                name = tuple_item[0]
                value = tuple_item[1]
                # Apply recursive truncation to handle nested structures
                truncated_value = AttributePolisher.apply_truncation_recursive(value, name=name)
                if len(tuple_item) == 3:
                    yield name, truncated_value, tuple_item[2]
                else:
                    yield name, truncated_value
        else:
            yield item


def make_truncated_wrapper(model: BaseModel) -> Any:
    """Create a wrapper that provides truncated __rich_repr__ for a BaseModel.

    This dynamically creates a class with the same name as the model's class,
    so Rich's Pretty displays the correct type name while applying
    AttributePolisher truncation to long string values.
    """
    model_class_name = model.__class__.__name__

    def rich_repr_method(_self: Any) -> RichReprResult:
        # Call BaseModel's __rich_repr__ directly to avoid recursion if model is a CustomBaseModel
        base_repr = BaseModel.__rich_repr__(model)  # type: ignore[misc, arg-type]
        return _truncated_rich_repr_from_items(base_repr)

    # Create a dynamic class with the correct name
    wrapper_class = type(
        model_class_name,
        (),
        {
            "__rich_repr__": rich_repr_method,
        },
    )

    return wrapper_class()


class CustomBaseModel(BaseModel):
    @override
    def __rich_repr__(self) -> RichReprResult:
        # Use super().__rich_repr__() to get base items, avoiding recursion
        yield from _truncated_rich_repr_from_items(super().__rich_repr__())  # type: ignore[misc]

    @override
    def __repr_args__(self) -> Sequence[tuple[str | None, Any]]:
        processed_args: list[tuple[str | None, Any]] = []
        for name, value in super().__repr_args__():
            if AttributePolisher.should_truncate(value=value):
                truncated_value = AttributePolisher.get_truncated_value(value)
                processed_args.append((name, truncated_value))
            else:
                processed_args.append((name, value))
        return processed_args

    def model_dump_truncated(self, **kwargs: Any) -> Any:
        """Dump the model to a dictionary with serialize_as_any=True and apply

        AttributePolisher truncation to fields that should be truncated.
        Handles nested attributes recursively.

        Args:
            **kwargs: Additional keyword arguments to pass to model_dump

        Returns:
            Dictionary with truncated values where appropriate

        """
        # Get the model dump with serialize_as_any=True
        dumped_data = self.model_dump(**kwargs)

        # Apply truncation logic recursively using the shared utility
        return AttributePolisher.apply_truncation_recursive(dumped_data)
