from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from rich.text import Text
from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.misc.pretty import plain_markup_text

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.core.memory.working_memory import WorkingMemory

PIPE_CODE = "list_the_names"


class ListingOperator(PipeOperator[PipeOutput]):
    """An operator whose live run outputs a list of texts, as many as it is built with, and does nothing else."""

    type: Any = "PipeFunc"
    nb_items: int = 0

    @override
    def validate_inputs_with_library(self) -> None: ...

    @override
    def validate_inputs_static(self) -> None: ...

    @override
    def validate_output_with_library(self) -> None: ...

    @override
    def validate_output_static(self) -> None: ...

    @override
    async def _validate_before_run(self, **kwargs: Any) -> None: ...

    @override
    async def _validate_after_run(self, **kwargs: Any) -> None: ...

    @override
    def required_variables(self) -> set[str]:
        return set()

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> Any:
        return self.inputs

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        items = [TextContent(text=f"name {index_item}") for index_item in range(self.nb_items)]
        main_stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT),
            content=ListContent[TextContent](items=items),
            name="names",
        )
        return PipeOutput(
            working_memory=WorkingMemoryFactory.make_from_single_stuff(main_stuff),
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )


@pytest.mark.asyncio
class TestOperatorOutputTitle:
    @pytest.mark.parametrize(
        ("nb_items", "multiplicity"),
        [
            pytest.param(0, "[empty list]", id="empty"),
            pytest.param(1, "[1 item]", id="one"),
            pytest.param(3, "[3 items]", id="several"),
        ],
    )
    async def test_the_output_title_keeps_the_list_multiplicity(self, mocker: MockerFixture, nb_items: int, multiplicity: str) -> None:
        """The bracketed multiplicity after the output concept reads as written in both the rich and the poor printer's reading."""
        pretty_print_spy = mocker.patch.object(Stuff, "pretty_print_stuff", autospec=True)
        pipe = ListingOperator(
            code=PIPE_CODE,
            domain_code="test_output_title",
            description="An operator listing names",
            output=StuffSpec(concept=ConceptFactory.make_native_concept(NativeConceptCode.TEXT)),
            nb_items=nb_items,
        )

        await pipe.live_run_pipe(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-output-title")
            ),
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, batch_max_concurrency=1, pipe_stack_limit=10, pipe_stack=[PIPE_CODE]),
        )

        title = pretty_print_spy.call_args.kwargs["title"]
        expected = f"Output of pipe {PIPE_CODE} → Text {multiplicity}"
        assert Text.from_markup(title).plain == expected
        assert plain_markup_text(markup=title) == expected
