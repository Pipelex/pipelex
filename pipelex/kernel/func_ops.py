"""Function-call operator semantics: invocation, return coercion, memory write-back.

These are the functions the interpreter's default `PipeFunc` executor calls, and the ones a
programmatic caller invokes on a `RuntimeBoot`-only process. Unlike every other operator's ops module
this one reads no hub at all: running a function touches no inference service, and the function is
handed in already resolved. Where a `PipeFunc`'s function comes from, an import path from the root of
its method tree, is the interpreter's business (`pipelex.pipe_operators.func.pipe_func_python`); the
kernel is handed the callable, as every other op is handed resolved values.

`call_function` is where the semantics actually live — async-vs-sync dispatch and the
return coercion that lets a function return a bare `str` or a `list` and still produce one
`StuffContent` shape downstream. It is deliberately separate from `run_func`, because the
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


async def call_function(*, function: Callable[..., Any], memory: WorkingMemory, function_name: str | None = None) -> FuncCallResult:
    """Run a function against the memory, and coerce what it returns.

    The function is arbitrary user code and its failure surface is not enumerable, so nothing is
    caught here: a caller that can add context to a failure (the interpreter's operator decorates it
    with the step's inputs and declared output) wraps this call instead.

    A sync function runs on a worker thread so it cannot block the event loop. The coercion accepts
    the three shapes the language allows an author to return — a `StuffContent`, a list of them, or a
    bare `str` — and normalizes them so every caller downstream sees one shape.

    Args:
        function: The function, called with the memory as its `working_memory` keyword.
        memory: The working memory the function reads.
        function_name: The name the step calls the function by, for messages; its qualified name when not given.
    """
    label = function_name or getattr(function, "__qualname__", repr(function))

    if inspect.iscoroutinefunction(function):
        func_output_object = await function(working_memory=memory)
    else:
        func_output_object = await asyncio.to_thread(function, working_memory=memory)

    content: StuffContent
    if isinstance(func_output_object, StuffContent):
        content = func_output_object
    elif isinstance(func_output_object, list):
        func_result_list = cast("list[StuffContent]", func_output_object)
        content = ListContent(items=func_result_list)
    elif isinstance(func_output_object, str):
        content = TextContent(text=func_output_object)
    else:
        msg = f"Function '{label}' must return a StuffContent, a list or a string, got {type(func_output_object)}"
        raise FuncOutputTypeError(msg)

    return FuncCallResult(
        content=content,
        function_module=getattr(function, "__module__", None),
        function_qualname=getattr(function, "__qualname__", label),
    )


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
