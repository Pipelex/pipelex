import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.tracing_assembly import TracingAssembly, assemble_tracing, assemble_tracing_on_output
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.trace_events import UsageReportEvent

_MODULE = "pipelex.pipe_run.tracing_assembly"


def _make_usage_event(pipeline_run_id: str, node_id: str) -> UsageReportEvent:
    """A UsageReportEvent carrying a real LLMTokensUsage (so the aggregator returns it)."""
    metadata = JobMetadata(user_id="tracing-assembly-test", pipeline_run_id=pipeline_run_id)
    tokens_usage = LLMTokensUsage(
        job_metadata=metadata,
        inference_model_name="fake_model",
        inference_model_id="fake_model_id",
        unit_costs={CostCategory.INPUT: 0.0, CostCategory.OUTPUT: 0.0},
        nb_tokens_by_category={TokenCategory.INPUT: 3, TokenCategory.OUTPUT: 5},
    )
    return UsageReportEvent(
        pipeline_run_id=pipeline_run_id,
        workflow_id="direct",
        timestamp=datetime.now(timezone.utc),
        sequence=0,
        node_id=node_id,
        tokens_usage=tokens_usage,
    )


class TestTracingAssembly:
    def _enable_tracing(self, mocker: MockerFixture) -> None:
        mock_config = mocker.patch(f"{_MODULE}.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

    def _disable_tracing(self, mocker: MockerFixture) -> None:
        mock_config = mocker.patch(f"{_MODULE}.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = False

    def test_returns_empty_when_tracing_disabled(self, mocker: MockerFixture) -> None:
        self._disable_tracing(mocker)
        make_event_log = mocker.patch(f"{_MODULE}.make_event_log")

        result = assemble_tracing(pipeline_run_id="plr", assemble_graph=True, assemble_usage=True)

        make_event_log.assert_not_called()
        assert result == TracingAssembly()

    def test_returns_empty_when_neither_concern_requested(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        make_event_log = mocker.patch(f"{_MODULE}.make_event_log")

        result = assemble_tracing(pipeline_run_id="plr", assemble_graph=False, assemble_usage=False)

        make_event_log.assert_not_called()
        assert result == TracingAssembly()

    def test_empty_events_returns_empty(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(return_value=[])
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)
        assemble = mocker.patch(f"{_MODULE}.GraphSpecAssembler.assemble")

        result = assemble_tracing(pipeline_run_id="plr", assemble_graph=True, assemble_usage=True)

        assert result.graph_spec is None
        assert result.tokens_usages is None
        assemble.assert_not_called()
        event_log.close.assert_called_once()

    def test_usage_only_aggregates_and_skips_graph(self, mocker: MockerFixture) -> None:
        """Costs-only: usage is aggregated, graph_spec stays None even with events present, assembler untouched."""
        self._enable_tracing(mocker)
        usage_event = _make_usage_event("plr-usage", "plr-usage:node_0")
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(return_value=[usage_event])
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)
        assemble = mocker.patch(f"{_MODULE}.GraphSpecAssembler.assemble")

        result = assemble_tracing(pipeline_run_id="plr-usage", assemble_graph=False, assemble_usage=True)

        assert result.graph_spec is None
        assert result.tokens_usages == [usage_event.tokens_usage]
        assemble.assert_not_called()

    def test_graph_only_assembles_and_skips_usage(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        usage_event = _make_usage_event("plr-graph", "plr-graph:node_0")
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(return_value=[usage_event])
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)
        sentinel_graph = mocker.MagicMock()
        assemble = mocker.patch(f"{_MODULE}.GraphSpecAssembler.assemble", return_value=sentinel_graph)

        result = assemble_tracing(
            pipeline_run_id="plr-graph",
            assemble_graph=True,
            assemble_usage=False,
            domain_code="dom",
            main_pipe_code="main",
        )

        assert result.graph_spec is sentinel_graph
        assert result.tokens_usages is None
        assemble.assert_called_once()

    def test_graph_and_usage_both_assembled(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        usage_event = _make_usage_event("plr-both", "plr-both:node_0")
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(return_value=[usage_event])
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)
        sentinel_graph = mocker.MagicMock()
        mocker.patch(f"{_MODULE}.GraphSpecAssembler.assemble", return_value=sentinel_graph)

        result = assemble_tracing(pipeline_run_id="plr-both", assemble_graph=True, assemble_usage=True)

        assert result.graph_spec is sentinel_graph
        assert result.tokens_usages == [usage_event.tokens_usage]

    def test_read_oserror_sets_error_on_requested_concerns(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(side_effect=OSError("file vanished"))
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)

        result = assemble_tracing(pipeline_run_id="plr", assemble_graph=True, assemble_usage=True)

        assert result.graph_spec is None
        assert result.tokens_usages is None
        assert result.graph_assembly_error is not None
        assert result.usage_assembly_error is not None
        event_log.close.assert_called_once()

    def test_read_botocore_errors_are_caught(self, mocker: MockerFixture) -> None:
        """DynamoDB backend failures degrade to an assembly error, never failing the run. Covers BOTH botocore
        base classes (siblings, neither a subclass of the other): ClientError (service-side throttle / auth)
        and BotoCoreError subclasses (transport / credential / timeout, e.g. EndpointConnectionError).
        """
        botocore_exceptions = pytest.importorskip("botocore.exceptions")
        client_error = botocore_exceptions.ClientError(
            error_response={"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "throttled"}},
            operation_name="Query",
        )
        transport_error = botocore_exceptions.EndpointConnectionError(endpoint_url="https://dynamodb.test")
        for backend_error in (client_error, transport_error):
            self._enable_tracing(mocker)
            event_log = mocker.MagicMock()
            event_log.read_events = mocker.MagicMock(side_effect=backend_error)
            mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)

            result = assemble_tracing(pipeline_run_id="plr", assemble_graph=True, assemble_usage=True)

            assert result.graph_spec is None, backend_error
            assert result.tokens_usages is None, backend_error
            assert result.graph_assembly_error is not None, backend_error
            assert result.usage_assembly_error is not None, backend_error
            event_log.close.assert_called_once()

    def test_read_error_only_marks_requested_concern(self, mocker: MockerFixture) -> None:
        """A costs-only read failure sets usage_assembly_error but never graph_assembly_error."""
        self._enable_tracing(mocker)
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(side_effect=json.JSONDecodeError("corrupt", doc="{", pos=0))
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)

        result = assemble_tracing(pipeline_run_id="plr", assemble_graph=False, assemble_usage=True)

        assert result.usage_assembly_error is not None
        assert result.graph_assembly_error is None

    def test_read_config_error_is_caught(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        mocker.patch(f"{_MODULE}.make_event_log", side_effect=PipelexConfigError("ndjson section missing"))

        result = assemble_tracing(pipeline_run_id="plr", assemble_graph=True, assemble_usage=False)

        assert result.graph_spec is None
        assert result.graph_assembly_error is not None

    def test_read_missing_dependency_is_caught(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        mocker.patch(f"{_MODULE}.make_event_log", side_effect=MissingDependencyError(dependency_name="boto3", extra_name="aws"))

        result = assemble_tracing(pipeline_run_id="plr", assemble_graph=True, assemble_usage=True)

        assert result.graph_assembly_error is not None
        assert result.usage_assembly_error is not None

    def test_graph_validation_error_still_aggregates_usage(self, mocker: MockerFixture) -> None:
        """A GraphSpec build failure records graph_assembly_error but leaves the usage aggregation intact."""
        self._enable_tracing(mocker)
        usage_event = _make_usage_event("plr-mixed", "plr-mixed:node_0")
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(return_value=[usage_event])
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)
        validation_error = ValidationError.from_exception_data(title="GraphSpec", line_errors=[])
        mocker.patch(f"{_MODULE}.GraphSpecAssembler.assemble", side_effect=validation_error)

        result = assemble_tracing(pipeline_run_id="plr-mixed", assemble_graph=True, assemble_usage=True)

        assert result.graph_spec is None
        assert result.graph_assembly_error is not None
        assert result.tokens_usages == [usage_event.tokens_usage]

    def test_unexpected_keyerror_propagates(self, mocker: MockerFixture) -> None:
        """Programming bugs (KeyError) propagate — proves tightening from a blanket except Exception."""
        self._enable_tracing(mocker)
        mocker.patch(f"{_MODULE}.make_event_log", side_effect=KeyError("unexpected_key"))

        with pytest.raises(KeyError):
            assemble_tracing(pipeline_run_id="plr", assemble_graph=True, assemble_usage=True)

    def test_tracing_assembly_round_trips_through_json(self) -> None:
        """TracingAssembly is the Temporal activity return type; its tokens_usages discriminated union
        must survive a model_dump_json → model_validate_json round-trip (proxy for the pydantic data
        converter that carries it across the activity boundary).
        """
        usage_event = _make_usage_event("plr-roundtrip", "plr-roundtrip:node_0")
        original = TracingAssembly(tokens_usages=[usage_event.tokens_usage])

        restored = TracingAssembly.model_validate_json(original.model_dump_json())

        assert restored.graph_spec is None
        assert restored.tokens_usages == [usage_event.tokens_usage]

    def test_on_output_applies_assembled_fields(self, mocker: MockerFixture) -> None:
        self._enable_tracing(mocker)
        usage_event = _make_usage_event("plr-out", "plr-out:node_0")
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(return_value=[usage_event])
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)
        sentinel_graph = mocker.MagicMock()
        mocker.patch(f"{_MODULE}.GraphSpecAssembler.assemble", return_value=sentinel_graph)

        pipe_output = PipeOutput(pipeline_run_id="plr-out")
        assemble_tracing_on_output(
            pipe_output=pipe_output,
            pipeline_run_id="plr-out",
            assemble_graph=True,
            assemble_usage=True,
        )

        assert pipe_output.graph_spec is sentinel_graph
        assert pipe_output.tokens_usages == [usage_event.tokens_usage]

    def test_on_output_leaves_fields_when_nothing_assembled(self, mocker: MockerFixture) -> None:
        """A no-op read leaves pipe_output's tracing fields untouched (no clobbering with None)."""
        self._enable_tracing(mocker)
        event_log = mocker.MagicMock()
        event_log.read_events = mocker.MagicMock(return_value=[])
        mocker.patch(f"{_MODULE}.make_event_log", return_value=event_log)

        pipe_output = PipeOutput(pipeline_run_id="plr-noop")
        assemble_tracing_on_output(
            pipe_output=pipe_output,
            pipeline_run_id="plr-noop",
            assemble_graph=True,
            assemble_usage=True,
        )

        assert pipe_output.graph_spec is None
        assert pipe_output.tokens_usages is None
        assert pipe_output.graph_assembly_error is None
        assert pipe_output.usage_assembly_error is None
