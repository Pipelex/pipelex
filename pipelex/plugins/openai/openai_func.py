import inspect
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, create_model


def create_pydantic_model_from_function(func: Callable[..., Any]) -> type[BaseModel]:
    """Create a Pydantic BaseModel from a function's signature.

    Args:
        func: The function to inspect. Its parameters become model fields.

    Returns:
        type[BaseModel]: A dynamically created Pydantic model class.

    Raises:
        ValueError: If the function has unsupported parameter kinds.

    """
    sig = inspect.signature(func)
    fields: dict[str, tuple[type[Any], Any]] = {
        name: (param.annotation, param.default if param.default is not inspect.Parameter.empty else ...) for name, param in sig.parameters.items()
    }
    model_name = func.__name__
    return create_model(__model_name=model_name, **fields)  # type: ignore[name-defined,call-overload,no-any-return] # pyright: ignore[reportCallIssue, reportUnknownVariableType]
