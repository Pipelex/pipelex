from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar, cast, get_args

from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticKnownError
from pydantic_core.core_schema import ErrorType
from typing_extensions import override

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.typing.validation_exceptions import InputFreeValueError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pydantic_core import ErrorDetails
    from rich.repr import Result as RichReprResult

BaseModelTypeVar = TypeVar("BaseModelTypeVar", bound=BaseModel)

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


def empty_list_factory_of(_: type[T]) -> Callable[[], list[T]]:
    def _factory() -> list[T]:
        return []

    return _factory


def empty_dict_factory_of(_key: type[K], *, _val: type[V] | None = None) -> Callable[[], dict[K, Any]]:
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
    other_errors: list[str]


# The error kinds the analysis lists under a heading of its own; every other kind is listed under
# "Other validation errors", so no error is left out of the message because another kind is present.
_LISTED_ERROR_KINDS = frozenset(
    {"missing", "extra_forbidden", "type_error", "value_error", "enum", "literal_error", "union_tag_not_found", "model_type"}
)


def analyze_pydantic_validation_error(exc: ValidationError) -> PydanticValidationErrorAnalysis:
    """Analyze a Pydantic ValidationError into a readable string with detailed error information.

    Every error is rendered: the kinds it lists get their own heading, and all the others (an
    ``int_parsing`` or ``string_type`` error, say) are rendered under "Other validation errors",
    whatever else is present.

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
    enum_errors: list[str] = []
    for err in exc.errors():
        if err["type"] == "enum":
            field_path = ".".join(map(str, err["loc"]))
            expected = err.get("ctx", {}).get("expected", "unknown")
            enum_errors.append(f"'{field_path}': invalid enum value '{err.get('input', 'unknown')}', expected {expected}")
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

    # Every kind without a heading of its own, rendered whatever else is present.
    other_errors = [
        f"{'.'.join(map(str, err['loc']))}: {err['type']}: {err['msg']}" for err in exc.errors() if err["type"] not in _LISTED_ERROR_KINDS
    ]
    if other_errors:
        error_msg += "\n\nOther validation errors:"
        for other_error in other_errors:
            error_msg += f"\n{other_error}"

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
        other_errors=other_errors,
    )


def format_pydantic_validation_error(exc: ValidationError) -> str:
    """Format a Pydantic ValidationError into a readable string with detailed error information.

    The text quotes the values pydantic refused, an invalid enum value or a literal it did not expect, so it is for a
    document whose author reads it: the caller's own method or the operator's configuration. A run's data, its inputs,
    a model's answer or a value a pipe built, is never refused through it: `format_validation_error_without_input`
    renders that refusal without the data.

    Args:
        exc: The Pydantic ValidationError exception

    Returns:
        A formatted string containing categorized validation errors

    """
    return analyze_pydantic_validation_error(exc).error_msg


#: The keys of a pydantic error's context whose values come from the schema, never from the input: the bounds a field
#: declares, the values, tags, schemes or version it expects, a discriminator's name, a pattern, and the class or the kind
#: of collection it validates into. A context holding any other key, the input's own tag, its length, or a parser's or
#: a validator's ``error`` text, which can quote the input, keeps its message out of the rendering.
SCHEMA_CONTEXT_KEYS = frozenset(
    {
        "gt",
        "ge",
        "lt",
        "le",
        "multiple_of",
        "min_length",
        "max_length",
        "max_digits",
        "decimal_places",
        "whole_digits",
        "expected",
        "expected_tags",
        "expected_schemes",
        "expected_version",
        "discriminator",
        "pattern",
        "class_name",
        "class",
        "field_type",
        "method_name",
        "tz_expected",
        "encoding",
    }
)

#: The error type of a key the model forbids, whose last location component is that key, as the caller sent it.
EXTRA_FORBIDDEN_ERROR_TYPE = "extra_forbidden"

#: The error type pydantic gives a validator's ``ValueError``, whose message is the validator's own text.
VALUE_ERROR_TYPE = "value_error"

#: Every error type pydantic itself knows how to word.
_PYDANTIC_ERROR_TYPES: frozenset[str] = frozenset(get_args(ErrorType))


def _pydantic_own_reason(*, error: ErrorDetails) -> str | None:
    """The error's message when nothing in it came from the input, or ``None`` when any of it may have.

    A validator's ``InputFreeValueError`` keeps its message, which declares it holds nothing of the value. Any other
    type pydantic does not know is a ``PydanticCustomError``'s, whose message the validator wrote. A known type is
    kept only when every key of its context is in ``SCHEMA_CONTEXT_KEYS``, so that its template is filled from the
    schema alone, and when its message is exactly the one pydantic renders for it, which a ``PydanticCustomError``
    reusing a built-in type's name with a message of its own is not.
    """
    error_type = error["type"]
    context = error.get("ctx")
    if error_type == VALUE_ERROR_TYPE and context is not None and isinstance(context.get("error"), InputFreeValueError):
        # A validator's refusal that declares its message holds nothing of the value: pydantic's "Value error, " prefix
        # and the validator's own sentence.
        return error["msg"]
    if error_type not in _PYDANTIC_ERROR_TYPES:
        # A type pydantic does not know, and so a `PydanticCustomError`'s, worded by the validator.
        return None
    if context is not None and not SCHEMA_CONTEXT_KEYS.issuperset(context):
        # A value of the context may come from the input, or be a validator's or a parser's own text.
        return None
    try:
        own_message = PydanticKnownError(cast("ErrorType", error_type), context).message()
    except (KeyError, TypeError, ValueError):
        # Not with the context its template needs: the message is not pydantic's.
        return None
    if own_message != error["msg"]:
        return None
    return own_message


def refusal_reason_without_input(*, error: ErrorDetails) -> str:
    """One error's reason, never anything of the input it refused: pydantic's own message, or else the error's type."""
    return _pydantic_own_reason(error=error) or error["type"]


def _error_location(*, error: ErrorDetails) -> str:
    """An error's dotted location, a forbidden key's stopping at its parent, since the key is the input's own text."""
    location_parts = error["loc"][:-1] if error["type"] == EXTRA_FORBIDDEN_ERROR_TYPE else error["loc"]
    return ".".join(str(part) for part in location_parts)


def validation_error_locations(*, validation_error: ValidationError) -> list[str]:
    """The dotted location of each error of a ``ValidationError``, once each and in order, without what it refused.

    A forbidden key's location stops at its parent, the key being the input's own text, and an error at the root has no
    location, so it adds none.
    """
    locations: list[str] = []
    for error in validation_error.errors(include_url=False, include_input=False):
        location = _error_location(error=error)
        if location and location not in locations:
            locations.append(location)
    return locations


def format_validation_error_without_input(*, validation_error: ValidationError) -> str:
    """Each error of a ``ValidationError`` as its location and its reason, never the input it refused.

    A ``ValidationError``'s own text, and the analysis `format_pydantic_validation_error` gives, quote the values pydantic
    refused, which on a run's data are its inputs, a model's answer or a value a pipe built, and no message, log line or
    view carries those. The reason is pydantic's own message, or the error's type where the message may hold something
    of the input, since a validator's text, or one of pydantic's templates, can quote the very value it rejected; a
    validator that raises ``InputFreeValueError`` declares its text holds none of it, and keeps it. A forbidden key's
    location stops at its parent, the key being the caller's own text.
    """
    located_reasons: list[str] = []
    for error in validation_error.errors(include_url=False, include_input=False):
        location = _error_location(error=error)
        reason = refusal_reason_without_input(error=error)
        located_reasons.append(f"{location}: {reason}" if location else reason)
    return "; ".join(located_reasons) or validation_error.title


def describe_exception_without_input(*, exc: BaseException) -> str:
    """The text of an exception, a ``ValidationError``'s written without the input it refused.

    Every other exception's text is kept as it is: a raise site of Pipelex writes no run's data into its message, and a
    foreign exception's own text is the operator's diagnosis.
    """
    if isinstance(exc, ValidationError):
        return format_validation_error_without_input(validation_error=exc)
    return str(exc)


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
    *,
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
