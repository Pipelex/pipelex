import types
from typing import Any, Union, get_args, get_origin


def unwrap_optional(annotation: Any) -> Any:
    """Unwrap an Optional annotation to its single non-None arm.

    Handles both `Optional[X]` / `Union[X, None]` (origin `typing.Union`) and the
    PEP 604 form `X | None` (origin `types.UnionType`). Only the Optional shape is
    unwrapped: a union with two or more non-None arms (e.g. `str | int | None`) is
    returned unchanged, as are non-union annotations.

    Args:
        annotation: The type annotation to unwrap

    Returns:
        The single non-None arm when the annotation is Optional-shaped, otherwise
        the annotation unchanged
    """
    origin = get_origin(annotation)
    if origin is not Union and origin is not types.UnionType:
        return annotation
    args = get_args(annotation)
    non_none_args = [arg for arg in args if arg is not type(None)]
    if len(non_none_args) < len(args) and len(non_none_args) == 1:
        return non_none_args[0]
    return annotation
