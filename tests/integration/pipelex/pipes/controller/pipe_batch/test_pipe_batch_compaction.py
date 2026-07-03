"""PipeBatch compaction (D4 bonus): a branch that resolves absent is dropped from the aggregated
list — the batch output contains only found items (compactMap), instead of crashing on the raising
main-stuff accessor.

The absence source is the phase-1 `continue` semantics: the branch is a PipeCondition that routes
matching items to a processing pipe and non-matching items to `continue` (declared-absent output).
"""

from typing import Callable, cast

import pytest

from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_pipe_library
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_optionals_batch"


def optionals_batch_shout_item(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=working_memory.get_stuff_as_str(name="item").upper())


_TEST_FUNCS = [optionals_batch_shout_item]


def _make_live_run_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)


def _build_compacting_batch() -> PipeBatch:
    """Batch over Text items whose branch keeps 'good *' items (shouted) and continues on the rest."""
    shout_pipe = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_batch_shout",
        blueprint=PipeFuncBlueprint(
            description="Uppercase the batch item",
            inputs={"item": "Text"},
            output="Text",
            function_name="optionals_batch_shout_item",
        ),
    )
    gate_pipe = PipeFactory[PipeCondition].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_batch_gate",
        blueprint=PipeConditionBlueprint(
            description="Keep items starting with 'good', continue on the rest",
            inputs={"item": "Text"},
            output="Text",
            expression_template="{% if item.text.startswith('good') %}keep{% else %}reject{% endif %}",
            outcomes={"keep": "opt_batch_shout"},
            default_outcome=SpecialOutcome.CONTINUE,
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [shout_pipe, gate_pipe]:
        pipe_library.add_new_pipe(pipe=pipe)

    batch = PipeFactory[PipeBatch].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_batch_compact",
        blueprint=PipeBatchBlueprint(
            description="Batch the gate over the items",
            branch_pipe_code="opt_batch_gate",
            output="Text",
            input_list_name="items",
            input_item_name="item",
            inputs={"items": "Text"},
        ),
    )
    pipe_library.add_new_pipe(pipe=batch)
    return batch


@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchCompaction:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    async def test_absent_branch_results_are_dropped(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Mixed items: rejected items resolve absent (continue) and are dropped from the list."""
        load_empty_library()
        batch = _build_compacting_batch()

        items_stuff = StuffFactory.make_stuff(
            concept=batch.inputs.get_required_stuff_spec("items").concept,
            content=ListContent[TextContent](
                items=[TextContent(text="good morning"), TextContent(text="bad day"), TextContent(text="good night")],
            ),
            name="items",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(items_stuff)

        pipe_output = await batch.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        list_content = pipe_output.main_stuff.content
        assert isinstance(list_content, ListContent)
        texts = [item.text for item in cast("ListContent[TextContent]", list_content).items]
        assert texts == ["GOOD MORNING", "GOOD NIGHT"]

    async def test_all_branches_absent_yields_empty_list(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Every item rejected: the batch still delivers a real (empty) list output."""
        load_empty_library()
        batch = _build_compacting_batch()

        items_stuff = StuffFactory.make_stuff(
            concept=batch.inputs.get_required_stuff_spec("items").concept,
            content=ListContent[TextContent](items=[TextContent(text="bad day"), TextContent(text="worse day")]),
            name="items",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(items_stuff)

        pipe_output = await batch.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        list_content = pipe_output.main_stuff.content
        assert isinstance(list_content, ListContent)
        assert cast("ListContent[TextContent]", list_content).items == []
