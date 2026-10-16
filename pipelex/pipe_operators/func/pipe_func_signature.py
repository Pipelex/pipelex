"""The calling convention a `PipeFunc`'s function must follow, checked on the imported function.

The function takes exactly one parameter, named `working_memory` and typed `WorkingMemory`, and declares a return type
that is a `StuffContent` subclass, such as `TextContent` or `ListContent[...]`. Reading the annotations takes
`get_type_hints`, which needs the imported module, so this check runs when the function's module is imported, as the
step first runs, never at validation: validation proves the form from the syntax tree without running Python
(`pipe_func_definition_check`).
"""

import inspect
from collections.abc import Callable
from typing import Any, get_origin, get_type_hints

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent


def pipe_func_signature_violation(*, func: Callable[..., Any]) -> str | None:
    """Why `func` does not follow the `PipeFunc` calling convention, or None when it does.

    Args:
        func: The imported function.

    Returns:
        None when the function is eligible, else a reason that completes the sentence "The function ...".
    """
    try:
        signature = inspect.signature(func)
    except (ValueError, TypeError) as exc:
        return f"has a signature that cannot be inspected: {exc}"

    params = list(signature.parameters.values())
    if not params:
        return "must have exactly one parameter named 'working_memory', but has no parameters"
    if len(params) > 1:
        return f"must have exactly one parameter named 'working_memory', but has {len(params)} parameters"
    param = params[0]
    if param.name != "working_memory":
        return f"must name its parameter 'working_memory', but names it '{param.name}'"

    try:
        type_hints = get_type_hints(func)
    except (NameError, TypeError) as exc:
        return f"has type annotations that cannot be resolved: {exc}"

    if "working_memory" not in type_hints:
        return "must annotate its parameter 'working_memory' with the type 'WorkingMemory'"
    param_type = type_hints["working_memory"]
    if param_type is not WorkingMemory:
        return f"must annotate its parameter 'working_memory' with the type 'WorkingMemory', but annotates it '{param_type}'"

    if "return" not in type_hints:
        return "must have a return type annotation that is a subclass of StuffContent"
    return_type = type_hints["return"]
    if _is_stuff_content_type(annotation=return_type):
        return None
    return f"must return a subclass of StuffContent, but its return type is '{return_type}'"


def _is_stuff_content_type(*, annotation: Any) -> bool:
    """Whether a return annotation is a `StuffContent` subclass, or a parametrized generic of one such as `ListContent[X]`."""
    if inspect.isclass(annotation) and issubclass(annotation, StuffContent):
        return True
    origin = get_origin(annotation)
    return inspect.isclass(origin) and issubclass(origin, StuffContent)
