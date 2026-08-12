"""Function-call operator semantics: registry lookup, invocation, return coercion, memory write-back.

These are the functions the interpreter's default `PipeFunc` executor calls, and the ones a
programmatic caller invokes on a `RuntimeBoot`-only process. Unlike every other operator's ops module
this one reads no hub at all: running a registered function touches no inference service, only the
process-global function registry.

`call_registered_function` is where the semantics actually live — async-vs-sync dispatch and the
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
from typing import cast

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.func_results import FuncCallResult, FuncResult
from pipelex.kernel.memory_ops import store_result
from pipelex.system.registries.func_registry import func_registry


async def call_registered_function(*, function_name: str, memory: WorkingMemory) -> FuncCallResult:
    """Resolve a registered function by name, run it against the memory, and coerce what it returns.

    The function is arbitrary user code and its failure surface is not enumerable, so nothing is
    caught here: a caller that can add context to a failure (the interpreter's operator decorates it
    with the step's inputs and declared output) wraps this call instead.

    A sync function runs on a worker thread so it cannot block the event loop. The coercion accepts
    the three shapes the language allows an author to return — a `StuffContent`, a list of them, or a
    bare `str` — and normalizes them so every caller downstream sees one shape.
    """
    function = func_registry.get_required_function(function_name)

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
        msg = f"Function '{function_name}' must return a StuffContent or a list, got {type(func_output_object)}"
        raise TypeError(msg)

    return FuncCallResult(
        content=content,
        function_module=getattr(function, "__module__", None),
        function_qualname=getattr(function, "__qualname__", function_name),
    )


async def run_func(
    *,
    memory: WorkingMemory,
    function_name: str,
    concept: Concept,
    result_name: str | None = None,
    result_code: str | None = None,
) -> FuncResult:
    """A whole func step, run in this process: call the registered function and store what it returned.

    Takes the output `concept` rather than deriving one, for the reason every other op does: turning
    a concept into anything is a library's business, and the kernel is handed the resolved value.
    """
    call_result = await call_registered_function(function_name=function_name, memory=memory)
    return FuncResult(
        memory=store_result(memory=memory, concept=concept, content=call_result.content, result_name=result_name, result_code=result_code),
        content=call_result.content,
        function_module=call_result.function_module,
        function_qualname=call_result.function_qualname,
    )
