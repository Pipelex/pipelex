"""The ad-hoc PipeBatch that `batch_over` synthesizes derives its code from the LOCAL code.

`SubPipe.pipe_code` is an in-body reference, so it is qualified (`domain.foo`), while
`PipeFactory.make_from_blueprint` takes `domain_code` separately. Suffixing the qualified ref hands
the factory `domain.foo_batch` as a *code*.

That does not corrupt the resulting ref, and it is worth being precise about why: `PipeAbstract` has a
`code` validator that strips a namespace prefix, so the built pipe ends up correct either way. What
the wrong derivation produces is a `log.warning` on **every batched run** — a permanent false alarm
telling the user their pipe code has a namespace prefix, about a code no user wrote.

So this test asserts on the warning, not on the ref: the ref is identical under both derivations, and
a test that asserted on it would pass against the bug it was written to catch.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_required_entry_pipe
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import BatchParams
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestBatchAdhocPipeRef:
    async def test_batching_a_qualified_sub_pipe_warns_about_nothing(
        self,
        caplog: pytest.LogCaptureFixture,
        mocker: MockerFixture,
        job_metadata: JobMetadata,
        load_test_library: Callable[[list[Path]], None],
    ):
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_batch")])

        branch_pipe = get_required_entry_pipe(pipe_code="uppercase_transformer")
        item_spec = branch_pipe.inputs.get_required_stuff_spec(variable_name="text_item")
        items_stuff = StuffFactory.make_stuff(
            concept=item_spec.concept,
            content=ListContent[TextContent](items=[TextContent(text="one"), TextContent(text="two")]),
            name="texts",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=items_stuff)

        # The synthesized batch pipe is never registered anywhere and never returned, so the only way
        # to read its ref is to intercept the job it is handed to.
        captured: list[Any] = []
        real_make_pipe_job = PipeJobFactory.make_pipe_job

        def capture(**kwargs: Any) -> Any:
            captured.append(kwargs["pipe"])
            return real_make_pipe_job(**kwargs)

        mocker.patch.object(PipeJobFactory, "make_pipe_job", side_effect=capture)

        sub_pipe = SubPipe(
            pipe_code=branch_pipe.pipe_ref,
            output_name="uppercased",
            batch_params=BatchParams(input_list_stuff_name="texts", input_item_stuff_name="text_item"),
        )
        with caplog.at_level("WARNING", logger="pipelex"):
            await sub_pipe.run_pipe(
                calling_pipe_code="test_caller",
                working_memory=working_memory,
                job_metadata=job_metadata,
                sub_pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            )

        assert captured, "SubPipe did not build a batch job"
        batch_pipe = captured[0]
        assert batch_pipe.code == "uppercase_transformer_batch"
        assert batch_pipe.pipe_ref == "test_integration1.uppercase_transformer_batch"

        # The discriminating assertion. Deriving from the qualified ref hands the factory
        # `test_integration1.uppercase_transformer_batch` as a code; the `PipeAbstract.code` validator
        # strips it back and warns — every batched run, about a code the user never wrote.
        assert "namespace prefix" not in caplog.text

    async def test_batching_a_pipe_with_a_cross_domain_output_keeps_the_output_concept(
        self,
        mocker: MockerFixture,
        job_metadata: JobMetadata,
        load_test_library: Callable[[list[Path]], None],
    ):
        """The ad-hoc batch blueprint carries the output as a full concept_ref, not a bare code.

        The blueprint is built with the sub-pipe's own ``domain_code``, so a bare output code would
        be re-resolved in that domain — a `StuffSpecFactoryError` when the concept only exists in
        the sibling domain, or silently the WRONG concept when the sub-pipe's domain happens to
        declare the same code. This test reddens under `output=sub_pipe.output.concept.code`.
        """
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_batch")])

        branch_pipe = get_required_entry_pipe(pipe_code="cross_domain_reporter")
        item_spec = branch_pipe.inputs.get_required_stuff_spec(variable_name="text_item")
        items_stuff = StuffFactory.make_stuff(
            concept=item_spec.concept,
            content=ListContent[TextContent](items=[TextContent(text="one"), TextContent(text="two")]),
            name="texts",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=items_stuff)

        captured: list[Any] = []
        real_make_pipe_job = PipeJobFactory.make_pipe_job

        def capture(**kwargs: Any) -> Any:
            captured.append(kwargs["pipe"])
            return real_make_pipe_job(**kwargs)

        mocker.patch.object(PipeJobFactory, "make_pipe_job", side_effect=capture)

        sub_pipe = SubPipe(
            pipe_code=branch_pipe.pipe_ref,
            output_name="reported",
            batch_params=BatchParams(input_list_stuff_name="texts", input_item_stuff_name="text_item"),
        )
        await sub_pipe.run_pipe(
            calling_pipe_code="test_caller",
            working_memory=working_memory,
            job_metadata=job_metadata,
            sub_pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
        )

        assert captured, "SubPipe did not build a batch job"
        batch_pipe = captured[0]
        assert batch_pipe.output.concept.concept_ref == "test_integration1.UppercaseText"
