"""The annotation of an open-typed structure field that never holds nothing.

A field naming `native.Anything`, or one whose type the author left unspecified, is generated as `Any`, and
`Any` admits `None`. The standard says a `required` field never holds nothing, and a binding step reading one
derives no absence from it, so a required open field holding `None` is an absence its readers ruled out.
`NonNullAny` is that field's annotation: any value but `None`.

Its JSON schema stays the open `{}` that `Any` has. The structure class's schema is what a model is asked
for, and `{"not": {"type": "null"}}`, the only spelling of "anything but null" that does not enumerate the
other types, is refused by the strict structured-output modes of several providers, so a model may still
answer `null` there and is held to this rule when its answer is validated.
"""

from typing import Annotated, Any

from pydantic import AfterValidator
from pydantic.fields import FieldInfo
from pydantic_core import PydanticCustomError


def _refuse_none(  # kw-only: ignore -- pydantic calls an AfterValidator positionally
    value: Any,
) -> Any:
    if value is None:
        error_type = "null_value"
        message = "Input should be a value, not null: this field never holds nothing"
        raise PydanticCustomError(error_type, message)
    return value


NonNullAny = Annotated[Any, AfterValidator(_refuse_none)]


def is_non_null_any(*, field_info: FieldInfo) -> bool:
    """Whether a class field is annotated `NonNullAny`, whose `Any` annotation, unlike a bare one, never admits `None`."""
    return any(isinstance(constraint, AfterValidator) and constraint.func is _refuse_none for constraint in field_info.metadata)
