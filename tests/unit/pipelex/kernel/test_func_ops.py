"""The func path's kernel-only arms.

`run_func` is the whole reason these tests exist: no interpreter test reaches it. `PipeFunc` rides
the *pluggable* executor — which may run the function in a sandbox or a Temporal activity — and then
stores the result, so it exercises `call_registered_function` (through the direct executor) and
`store_result` separately, never their composition. A programmatic caller on a `RuntimeBoot`-only
process rides exactly that composition, so it is tested here or nowhere.

The sync arm is the second one worth pinning: a plain `def` function must not be awaited directly,
it has to reach a worker thread, and a rewrite that dropped the `iscoroutinefunction` branch would
still pass every async-function test.
"""

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.func_ops import call_registered_function, run_func
from pipelex.system.registries.func_registry import func_registry

ASYNC_FUNCTION_NAME = "kernel_unit_test_async_func"

SYNC_FUNCTION_NAME = "kernel_unit_test_sync_func"

ASYNC_TEXT = "produced by the async function"

SYNC_TEXT = "produced by the sync function"

RESULT_NAME = "func_output"


# Being a coroutine function with nothing to await is the point: it is what selects the awaited arm.
async def _async_producer(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001, RUF029
    return TextContent(text=ASYNC_TEXT)


def _sync_producer(working_memory: WorkingMemory) -> TextContent:  # noqa: ARG001
    return TextContent(text=SYNC_TEXT)


@pytest.fixture
def registered_producers():
    func_registry.register_function(_async_producer, name=ASYNC_FUNCTION_NAME)
    func_registry.register_function(_sync_producer, name=SYNC_FUNCTION_NAME)
    try:
        yield
    finally:
        func_registry.unregister_function_by_name(ASYNC_FUNCTION_NAME)
        func_registry.unregister_function_by_name(SYNC_FUNCTION_NAME)


@pytest.mark.usefixtures("registered_producers")
@pytest.mark.asyncio(loop_scope="class")
class TestFuncOps:
    @pytest.mark.parametrize(
        ("function_name", "expected_text", "expected_qualname"),
        [
            pytest.param(ASYNC_FUNCTION_NAME, ASYNC_TEXT, _async_producer.__qualname__, id="async-function"),
            pytest.param(SYNC_FUNCTION_NAME, SYNC_TEXT, _sync_producer.__qualname__, id="sync-function-on-a-worker-thread"),
        ],
    )
    async def test_call_registered_function_runs_both_dispatch_arms(
        self,
        function_name: str,
        expected_text: str,
        expected_qualname: str,
    ) -> None:
        call_result = await call_registered_function(function_name=function_name, memory=WorkingMemoryFactory.make_empty())

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
            function_name=ASYNC_FUNCTION_NAME,
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            result_name=RESULT_NAME,
        )

        main_stuff = result.memory.get_main_stuff()
        assert main_stuff.stuff_name == RESULT_NAME
        assert isinstance(main_stuff.content, TextContent)
        assert main_stuff.content.text == ASYNC_TEXT
        assert result.content is main_stuff.content
        assert result.memory.get_stuff(name=RESULT_NAME).content is main_stuff.content
