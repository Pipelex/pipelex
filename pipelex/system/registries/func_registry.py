"""The `@pipe_func` marker: the opt-in that lets a `PipeFunc` step call a Python function.

A `PipeFunc` names its function by import path from the root of its method tree (`function_name =
"funcs.totals.compute_totals"`), and the function it names must carry this marker, so a `.mthds` file can never
call an arbitrary function such as `os.system`. The marker is Pipelex's, as is the calling convention it stands for:
one parameter named `working_memory` typed `WorkingMemory`, and a return type that is a `StuffContent`.

The process-wide function registry this module once held is retired: nothing registers a function anymore, and the
import path is the only name a function has. The module keeps its name because every method's Python imports the
marker from here, as `from pipelex.system.registries.func_registry import pipe_func`, and that line must keep working.

The marker takes no argument. Its former `name=` argument, which registered a function under another name, is gone
with the registry: `pipelex fix function-names` rewrites a method that used it.
"""

from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

#: The attribute the marker sets on the function it decorates.
PIPE_FUNC_MARKER = "_is_pipe_func"

#: The module the marker is imported from, which the static check of a `PipeFunc`'s module recognizes.
PIPE_FUNC_MARKER_MODULE = "pipelex.system.registries.func_registry"

#: The name of the marker in its module.
PIPE_FUNC_MARKER_NAME = "pipe_func"


def pipe_func() -> Callable[[T], T]:
    """Mark a function as callable from a `PipeFunc` step, which names it by its import path.

    The function must be a top-level `def` or `async def` of its module, decorated with this marker directly or
    through an import alias, and follow the calling convention: exactly one parameter named `working_memory` of type
    `WorkingMemory`, and a return type that is a `StuffContent` subclass, such as `TextContent` or `ListContent[...]`.
    An `async def` is awaited; a plain `def` runs on a worker thread.

    Example:
        @pipe_func()
        async def compute_totals(working_memory: WorkingMemory) -> TextContent:
            ...

    Returns:
        The decorator, which returns the function unchanged, marked.
    """

    def decorator(func: T) -> T:
        setattr(func, PIPE_FUNC_MARKER, True)
        return func

    return decorator


def is_marked_pipe_func(*, func: Any) -> bool:
    """Whether `func` carries the `@pipe_func` marker."""
    return getattr(func, PIPE_FUNC_MARKER, None) is True
