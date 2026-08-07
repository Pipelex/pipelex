"""The run-scoped state `PipelexKernel` holds, and what each step inherits from it.

`test_usage_parity.py` measures the end of this chain — that a kernel run's usage records match an
interpreter run's. These pin the links, because a parity failure there says "no events" without
saying which link dropped: the run-level metadata, the per-step copy, or the run mode.
"""

from uuid import UUID

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.exceptions import StuffContentTypeError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.kernel.memory_ops import (
    extract_main_content,
    extract_main_content_as_list,
    extract_named_content,
    extract_named_content_as_list,
    store_result,
)
from pipelex.kernel.pipelex_kernel import PipelexKernel
from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext

_GRAPH_ID = "kernel-run-state"


def _trace_context() -> TraceContext:
    return TraceContext(
        graph_id=_GRAPH_ID,
        data_inclusion=DataInclusionConfig(
            stuff_json_content=False,
            stuff_text_content=False,
            stuff_html_content=False,
            error_stack_traces=False,
            pipe_and_concept_registry=False,
        ),
        emit_graph_events=False,
        emit_usage_events=True,
    )


class TestPipelexKernelRunState:
    def test_a_supplied_trace_context_becomes_the_runs_identity(self) -> None:
        """Passing a context adopts its graph_id as the run id — the two are one identity.

        Letting them diverge would scatter a single run's usage events across two ids: the
        registered-context emit path stamps the event log's, the runner fallback stamps the
        metadata's, so a read-back keyed on either would silently miss the other's.
        """
        trace_context = _trace_context()

        kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user", trace_context=trace_context)

        assert kernel.job_metadata.pipeline_run_id == _GRAPH_ID
        assert kernel.job_metadata.trace_context == trace_context

    def test_without_a_trace_context_the_run_mints_its_own_id_and_traces_nothing(self) -> None:
        """The default stays what it was: a fresh run id, and no context for the leaf to emit against."""
        first = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user")
        second = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user")

        assert first.job_metadata.trace_context is None
        assert first.job_metadata.pipeline_run_id != second.job_metadata.pipeline_run_id

    def test_each_step_inherits_the_trace_context_and_carries_its_own_run_id(self) -> None:
        """The per-step copy: same trace context (so every step attributes to it), distinct pipe_run_id."""
        kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user", trace_context=_trace_context())

        first_step = kernel.make_step_metadata()
        second_step = kernel.make_step_metadata()

        assert first_step.trace_context == kernel.job_metadata.trace_context
        assert second_step.trace_context == kernel.job_metadata.trace_context
        assert first_step.pipeline_run_id == second_step.pipeline_run_id == _GRAPH_ID
        assert first_step.pipe_run_id != second_step.pipe_run_id
        # Computed fresh per step by whoever opens the span, and a kernel call opens none.
        assert first_step.otel_context is None

    def test_a_step_names_the_pipe_it_is_running_when_told_which(self) -> None:
        """The kernel tier's half of what the interpreter already does in `pipe_abstract`.

        Anything that attributes work by `pipe_code` — log correlation, usage accounting, the
        per-step labelling a distributed backend derives — sees an anonymous step without this.
        """
        kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user")

        assert kernel.make_step_metadata(pipe_code="answer_question").pipe_code == "answer_question"

    def test_an_unnamed_step_does_not_erase_the_runs_own_pipe_code(self) -> None:
        """The erasure trap: `copy_with_update` applies whatever it is handed, `None` included.

        Passing `pipe_code=None` through unconditionally would turn an optional enrichment into a
        silent wipe of the run-level value for every caller that never asked for the feature. The
        key must be omitted, not passed as None — so this constructs a run that HAS a run-level
        `pipe_code`, which no caller in the tree does today.
        """
        kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user")
        kernel.job_metadata.pipe_code = "set_at_run_level"

        assert kernel.make_step_metadata().pipe_code == "set_at_run_level"

    def test_the_step_id_source_is_injectable_and_defaults_to_uuid(self) -> None:
        """A workflow-hosted kernel must be able to supply a replay-safe id source.

        The kernel cannot import `temporalio` — that is the whole point of the tier — so the
        replay-safe source arrives from outside. ⚠ Measured 2026-08-07: `uuid4()` in workflow code
        does NOT currently raise on replay (see `kernel-step-identity-plan.md`), so this closes a
        latent trap rather than a live defect; Phase 3's usage wiring is the consumer that would
        first observe the drift.
        """
        minted: list[str] = []

        def _source() -> str:
            minted.append(f"step-{len(minted)}")
            return minted[-1]

        kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user", step_id_source=_source)

        assert kernel.make_step_metadata().pipe_run_id == "step-0"
        assert kernel.make_step_metadata().pipe_run_id == "step-1"

        default_kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user")
        first_default = default_kernel.make_step_metadata().pipe_run_id
        assert first_default is not None
        assert UUID(first_default).version == 4
        assert first_default != default_kernel.make_step_metadata().pipe_run_id

    def test_mock_usage_rides_the_execution_mode_contract(self) -> None:
        """The DRY sub-flag lands on the carrier every cogt leaf reads off its assignment."""
        kernel = PipelexKernel.make(run_mode=PipeRunMode.DRY, user_id="test-user", is_mock_usage=True)

        assert kernel.cogt_run_params.run_mode.is_dry
        assert kernel.cogt_run_params.is_mock_usage

    def test_the_memory_boundary_reads_back_what_was_written(self) -> None:
        """`store_result` writes the main stuff; both extraction helpers read it typed."""
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)
        memory = store_result(
            memory=WorkingMemoryFactory.make_empty(),
            concept=concept,
            content=TextContent(text="written by the kernel"),
            result_name="written",
        )

        assert extract_main_content(memory=memory, content_type=TextContent).text == "written by the kernel"
        assert extract_named_content(memory=memory, name="written", content_type=TextContent).text == "written by the kernel"

    def test_the_memory_boundary_reads_back_a_multiple_output_result_typed(self) -> None:
        """The list reads narrow a `ListContent` down to its items, which the single-content reads cannot.

        That is the whole reason they exist: a multiple-output kernel call stores one `ListContent`, and
        asking for the bare item class raises rather than unwrapping it.
        """
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)
        memory = store_result(
            memory=WorkingMemoryFactory.make_empty(),
            concept=concept,
            content=ListContent(items=[TextContent(text="first"), TextContent(text="second")]),
            result_name="written",
        )

        for extracted in (
            extract_main_content_as_list(memory=memory, item_type=TextContent),
            extract_named_content_as_list(memory=memory, name="written", item_type=TextContent),
        ):
            assert [item.text for item in extracted.items] == ["first", "second"]

        with pytest.raises(StuffContentTypeError):
            extract_main_content(memory=memory, content_type=TextContent)
