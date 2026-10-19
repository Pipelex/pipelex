"""Function-call operator semantics: invocation, return coercion, memory write-back.

These are the functions the interpreter's default `PipeFunc` executor calls, and the ones a
programmatic caller invokes on a `RuntimeBoot`-only process. Unlike every other operator's ops module
this one reads no hub at all: running a function touches no inference service, and the function is
handed in already resolved. Where a `PipeFunc`'s function comes from, an import path from the root of
its method tree, is the interpreter's business (`pipelex.pipe_operators.func.pipe_func_python`); the
kernel is handed the callable, as every other op is handed resolved values.

`call_function` is where the semantics actually live — async-vs-sync dispatch (`invoke_function`) and
the return coercion (`coerce_function_output`) that lets a function return a bare `str` or a `list` and
still produce one `StuffContent` shape downstream. The two are apart so that a caller can tell the
function's own failure from the coercion refusing what it returned, which is the step's output failing.
It is deliberately separate from `run_func`, because the
interpreter's out-of-process executors (a sandbox, a Temporal activity) replace *the call* and keep
the write-back; `run_func` is the in-process composition of the two, and the entry point a
programmatic caller wants.

One seam is deliberately *not* here: **choosing where the function runs.** Executor selection is
configured deployment machinery, and its protocol is typed on interpreter models.
"""

import asyncio
import inspect
from collections.abc import Callable
from typing import Any, cast

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.exceptions import FuncOutputTypeError
from pipelex.kernel.func_results import FuncCallResult, FuncResult
from pipelex.kernel.memory_ops import store_result


async def invoke_function(*, function: Callable[..., Any], memory: WorkingMemory) -> Any:
    """Run a function against the memory, and return what it returned, as it returned it.

    The call alone, apart from the coercion of its result (`coerce_function_output`), so that a caller wrapping the
    function's own failures wraps nothing else. The function is arbitrary user code and its failure surface is not
    enumerable, so nothing is caught here. A sync function runs on a worker thread so it cannot block the event loop.

    Args:
        function: The function, called with the memory as its `working_memory` keyword.
        memory: The working memory the function reads.
    """
    if inspect.iscoroutinefunction(function):
        return await function(working_memory=memory)
    return await asyncio.to_thread(function, working_memory=memory)


def coerce_function_output(*, function: Callable[..., Any], function_output: Any, function_name: str | None = None) -> FuncCallResult:
    """Coerce what a function returned into one `StuffContent` shape, refusing any other shape as the step's output.

    The coercion accepts the three shapes the language allows an author to return — a `StuffContent`, a list of them,
    or a bare `str` — and normalizes them so every caller downstream sees one shape.

    Args:
        function: The function that returned it, whose module and qualified name ride on the result.
        function_output: What the function returned.
        function_name: The name the step calls the function by, for messages; its qualified name when not given.

    Raises:
        FuncOutputTypeError: The function returned another shape, or a list holding anything but stuff contents.
    """
    label = function_name or getattr(function, "__qualname__", repr(function))

    content: StuffContent
    if isinstance(function_output, StuffContent):
        content = function_output
    elif isinstance(function_output, list):
        output_items = cast("list[Any]", function_output)
        for index_item, output_item in enumerate(output_items):
            if not isinstance(output_item, StuffContent):
                msg = f"Function '{label}' must return a list of StuffContent, got {type(output_item)} at index {index_item}"
                raise FuncOutputTypeError(msg)
        content = ListContent(items=cast("list[StuffContent]", output_items))
    elif isinstance(function_output, str):
        content = TextContent(text=function_output)
    else:
        msg = f"Function '{label}' must return a StuffContent, a list or a string, got {type(function_output)}"
        raise FuncOutputTypeError(msg)

    return FuncCallResult(
        content=content,
        function_module=getattr(function, "__module__", None),
        function_qualname=getattr(function, "__qualname__", label),
    )


async def call_function(*, function: Callable[..., Any], memory: WorkingMemory, function_name: str | None = None) -> FuncCallResult:
    """Run a function against the memory, and coerce what it returns.

    The composition of `invoke_function` and `coerce_function_output`. Nothing is caught here: a caller that can add
    context to a failure (the interpreter's operator decorates it with the step's inputs and declared output) wraps
    the call instead, and a caller that must tell the function's own failure from the coercion's calls the two apart.

    Args:
        function: The function, called with the memory as its `working_memory` keyword.
        memory: The working memory the function reads.
        function_name: The name the step calls the function by, for messages; its qualified name when not given.

    Raises:
        FuncOutputTypeError: The function returned a shape the coercion refuses.
    """
    function_output = await invoke_function(function=function, memory=memory)
    return coerce_function_output(function=function, function_output=function_output, function_name=function_name)


async def run_func(
    *,
    memory: WorkingMemory,
    function: Callable[..., Any],
    concept: Concept,
    result_name: str | None = None,
    result_code: str | None = None,
) -> FuncResult:
    """A whole func step, run in this process: call the function and store what it returned.

    Takes the `function` and the output `concept` rather than deriving them, for the reason every other
    op does: resolving a function or turning a concept into anything is a library's business, and the
    kernel is handed the resolved values.
    """
    call_result = await call_function(function=function, memory=memory)
    return FuncResult(
        memory=store_result(memory=memory, concept=concept, content=call_result.content, result_name=result_name, result_code=result_code),
        content=call_result.content,
        function_module=call_result.function_module,
        function_qualname=call_result.function_qualname,
    )
