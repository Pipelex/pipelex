import kajson

from pipelex.system.data_inclusion_config import DataInclusionConfig
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.trace_context import TraceContext


def _make_job_metadata(*, trace_context: TraceContext | None) -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="u", pipeline_run_id="run_7Qd2kV"),
        trace_context=trace_context,
    )


def _make_batch_context() -> TraceContext:
    """The context a batch at `filings.review_filings/step_3` hands the pipes it runs, in attempt 1 of the run."""
    return TraceContext(
        graph_id="run_7Qd2kV",
        parent_node_id="run_7Qd2kV:node_9",
        node_sequence=10,
        data_inclusion=DataInclusionConfig(stuff_json_content=False, error_stack_traces=False, pipe_and_concept_registry=False),
        run_mode=PipeRunMode.LIVE,
        parent_path="filings.review_filings/step_3",
        chain=[ExecutionAttempt(execution="exec-run", attempt=1)],
    )


class TestJobMetadataChildPlace:
    def test_a_child_place_rides_on_a_copy_of_the_trace_context(self) -> None:
        batch_metadata = _make_job_metadata(trace_context=_make_batch_context())

        item_metadata = batch_metadata.for_child_at(segment="item_2")

        assert item_metadata.trace_context is not None
        assert (item_metadata.trace_context.parent_path, item_metadata.trace_context.child_segment) == ("filings.review_filings/step_3", "item_2")
        assert batch_metadata.trace_context is not None
        assert batch_metadata.trace_context.child_segment is None

    def test_without_a_trace_context_there_is_no_place_to_name(self) -> None:
        untraced_metadata = _make_job_metadata(trace_context=None)
        assert untraced_metadata.for_child_at(segment="item_2") is untraced_metadata

    def test_a_batch_items_metadata_read_back_keeps_its_path_prefix_and_lineage(self) -> None:
        """The item's metadata crosses to the execution running the item as a workflow's input does, and keeps its place."""
        item_metadata = _make_job_metadata(trace_context=_make_batch_context()).for_child_at(segment="item_2")

        for recovered in (JobMetadata.model_validate_json(item_metadata.model_dump_json()), kajson.loads(kajson.dumps(item_metadata))):
            assert isinstance(recovered, JobMetadata)
            recovered_context = recovered.trace_context
            assert recovered_context is not None
            assert (recovered_context.parent_path, recovered_context.child_segment, recovered_context.chain) == (
                "filings.review_filings/step_3",
                "item_2",
                [ExecutionAttempt(execution="exec-run", attempt=1)],
            )
            assert recovered_context.invocation_path(pipe_ref="filings.summarize_filing") == "filings.review_filings/step_3/item_2"
