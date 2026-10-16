"""The func path's kernel-only arms.

`run_func` is the whole reason these tests exist: no interpreter test reaches it. `PipeFunc` rides
the *pluggable* executor — which may run the function in a sandbox or a Temporal activity — and then
stores the result, so it exercises `call_function` (through the direct executor) and
`store_result` separately, never their composition. A programmatic caller on a `RuntimeBoot`-only
process rides exactly that composition, so it is tested here or nowhere.

The sync arm is the second one worth pinning: a plain `def` function must not be awaited directly,
it has to reach a worker thread, and a rewrite that dropped the `iscoroutinefunction` branch would
still pass every async-function test.
"""

from collections.abc import Callable
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.exceptions import FuncOutputTypeError
from pipelex.kernel.func_ops import call_function, run_func

ASYNC_TEXT = "produced by the async function"

SYNC_TEXT = "produced by the sync function"

RESULT_NAME = "func_output"


# Being a coroutine function with nothing to await is the point: it is what selects the awaited arm.
async def _async_producer(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument, unused-async]
    return TextContent(text=ASYNC_TEXT)


def _sync_producer(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument]
    return TextContent(text=SYNC_TEXT)


def _number_producer(working_memory: WorkingMemory) -> int:  # ruff: ignore[unused-function-argument]
    return 42


def _dict_list_producer(working_memory: WorkingMemory) -> list[dict[str, int]]:  # ruff: ignore[unused-function-argument]
    return [{"parcel": 7}]


def _number_list_producer(working_memory: WorkingMemory) -> list[Any]:  # ruff: ignore[unused-function-argument]
    return [TextContent(text=SYNC_TEXT), 42]


@pytest.mark.asyncio(loop_scope="class")
class TestFuncOps:
    @pytest.mark.parametrize(
        ("function", "expected_text", "expected_qualname"),
        [
            pytest.param(_async_producer, ASYNC_TEXT, _async_producer.__qualname__, id="async-function"),
            pytest.param(_sync_producer, SYNC_TEXT, _sync_producer.__qualname__, id="sync-function-on-a-worker-thread"),
        ],
    )
    async def test_call_function_runs_both_dispatch_arms(
        self,
        function: Callable[..., Any],
        expected_text: str,
        expected_qualname: str,
    ) -> None:
        call_result = await call_function(function=function, memory=WorkingMemoryFactory.make_empty())

        assert isinstance(call_result.content, TextContent)
        assert call_result.content.text == expected_text
        assert call_result.function_module == __name__
        assert call_result.function_qualname == expected_qualname, (
            "the module and qualname ride back on the result because a caller that dispatched the call "
            "out-of-process no longer holds the function object to read them off"
        )

    async def test_run_func_returns_the_memory_holding_the_result(self) -> None:
        memory = WorkingMemoryFactory.make_empty()

        result = await run_func(
            memory=memory,
            function=_async_producer,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            result_name=RESULT_NAME,
        )

        main_stuff = result.memory.get_main_stuff()
        assert main_stuff.stuff_name == RESULT_NAME
        assert isinstance(main_stuff.content, TextContent)
        assert main_stuff.content.text == ASYNC_TEXT
        assert result.content is main_stuff.content
        assert result.memory.get_stuff(name=RESULT_NAME).content is main_stuff.content

    @pytest.mark.parametrize(
        ("function", "refused_type"),
        [
            pytest.param(_number_producer, "int", id="no-content"),
            pytest.param(_dict_list_producer, "dict", id="list-holding-a-dict"),
            pytest.param(_number_list_producer, "int", id="list-holding-a-number"),
        ],
    )
    async def test_a_function_returning_no_content_fails_the_step_output(self, function: Callable[..., Any], refused_type: str) -> None:
        """A registered function's wrong return shape is the step's output failing, not a runtime defect, and never a silent empty content."""
        with pytest.raises(FuncOutputTypeError, match=function.__name__) as exc_info:
            await call_function(function=function, memory=WorkingMemoryFactory.make_empty())

        assert f"<class '{refused_type}'>" in exc_info.value.message
        assert exc_info.value.resolve_error_code() == CoreCode.PIPE_OUTPUT_INVALID
