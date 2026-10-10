"""The annotation of an open-typed structure field that never holds nothing.

A field naming `native.Anything`, or one whose type the author left unspecified, is generated as `Any`, and
`Any` admits `None`. The standard says a `required` field never holds nothing, and a binding step reading one
derives no absence from it, so a required open field holding `None` is an absence its readers ruled out.
`NonNullAny` is that field's annotation: any value but `None`.

Its JSON schema stays the open `{}` that `Any` has. The structure class's schema is what a model is asked
for, and `{"not": {"type": "null"}}`, the only spelling of "anything but null" that does not enumerate the
other types, is refused by the strict structured-output modes of several providers, so a model may still
answer `null` there. In process, the answer is validated against the class itself, so that `null` is refused
and the model asked again; across a worker boundary, the class the worker rebuilds from the schema has a bare
`Any` there, so the `null` is only refused when the answer reaches the caller's class, failing the step.
"""

from typing import Annotated, Any

from pydantic import AfterValidator
from pydantic.fields import FieldInfo
from pydantic_core import PydanticCustomError

from pipelex.tools.typing.annotation_utils import annotation_admits_none


def _refuse_none(  # kw-only: ignore -- pydantic calls an AfterValidator positionally
    value: Any,
) -> Any:
    if value is None:
        error_type = "null_value"
        message = "Input should be a value, not null: this field never holds nothing"
        raise PydanticCustomError(error_type, message)
    return value


NonNullAny = Annotated[Any, AfterValidator(_refuse_none)]


def field_admits_none(*, field_info: FieldInfo) -> bool:
    """Whether a class field admits `None`, read off its annotation, `NonNullAny` being the one `Any` that does not."""
    is_non_null_any = any(isinstance(constraint, AfterValidator) and constraint.func is _refuse_none for constraint in field_info.metadata)
    return annotation_admits_none(annotation=field_info.annotation) and not is_non_null_any
