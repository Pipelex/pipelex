import json

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexConfigError
from pipelex.pipe_run.graph_assembly import assemble_graph_on_output
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.exceptions import EventLogReadError


class TestAssembleGraphOnOutput:
    def test_returns_when_tracing_disabled(self, mocker: MockerFixture) -> None:
        """When tracing is disabled, the function returns without touching pipe_output."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = False

        mock_make_event_log = mocker.patch("pipelex.pipe_run.graph_assembly.make_event_log")

        mock_pipe_output = mocker.MagicMock()
        original_graph_spec = mock_pipe_output.graph_spec

        assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-disabled")

        mock_make_event_log.assert_not_called()
        assert mock_pipe_output.graph_spec is original_graph_spec

    def test_swallows_oserror_with_warning(self, mocker: MockerFixture) -> None:
        """OSError from event log read is caught; pipe_output.graph_spec is left unchanged."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mock_event_log = mocker.MagicMock()
        mock_event_log.read_events = mocker.MagicMock(side_effect=OSError("file vanished"))
        mocker.patch(
            "pipelex.pipe_run.graph_assembly.make_event_log",
            return_value=mock_event_log,
        )

        mock_pipe_output = mocker.MagicMock()
        original_graph_spec = mock_pipe_output.graph_spec

        assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-oserror")

        assert mock_pipe_output.graph_spec is original_graph_spec
        mock_event_log.close.assert_called_once()

    def test_swallows_pipelex_config_error(self, mocker: MockerFixture) -> None:
        """PipelexConfigError from make_event_log is caught (broken tracing config doesn't fail the pipe)."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mocker.patch(
            "pipelex.pipe_run.graph_assembly.make_event_log",
            side_effect=PipelexConfigError("ndjson section missing"),
        )

        mock_pipe_output = mocker.MagicMock()
        original_graph_spec = mock_pipe_output.graph_spec

        assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-config")

        assert mock_pipe_output.graph_spec is original_graph_spec

    def test_swallows_missing_dependency_error(self, mocker: MockerFixture) -> None:
        """MissingDependencyError from make_event_log is caught (e.g., boto3 missing for DynamoDB)."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mocker.patch(
            "pipelex.pipe_run.graph_assembly.make_event_log",
            side_effect=MissingDependencyError(dependency_name="boto3", extra_name="aws"),
        )

        mock_pipe_output = mocker.MagicMock()
        original_graph_spec = mock_pipe_output.graph_spec

        assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-missing-dep")

        assert mock_pipe_output.graph_spec is original_graph_spec

    def test_swallows_validation_error(self, mocker: MockerFixture) -> None:
        """Pydantic ValidationError from GraphSpec construction is caught."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mock_event_log = mocker.MagicMock()
        mock_event_log.read_events = mocker.MagicMock(return_value=[mocker.MagicMock()])
        mocker.patch(
            "pipelex.pipe_run.graph_assembly.make_event_log",
            return_value=mock_event_log,
        )

        validation_error = ValidationError.from_exception_data(title="GraphSpec", line_errors=[])
        mocker.patch(
            "pipelex.pipe_run.graph_assembly.GraphSpecAssembler.assemble",
            side_effect=validation_error,
        )

        mock_pipe_output = mocker.MagicMock()
        original_graph_spec = mock_pipe_output.graph_spec

        assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-validation")

        assert mock_pipe_output.graph_spec is original_graph_spec
        mock_event_log.close.assert_called_once()

    def test_swallows_json_decode_error(self, mocker: MockerFixture) -> None:
        """json.JSONDecodeError from event log read is caught."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mock_event_log = mocker.MagicMock()
        mock_event_log.read_events = mocker.MagicMock(
            side_effect=json.JSONDecodeError("corrupt", doc="{", pos=0),
        )
        mocker.patch(
            "pipelex.pipe_run.graph_assembly.make_event_log",
            return_value=mock_event_log,
        )

        mock_pipe_output = mocker.MagicMock()
        original_graph_spec = mock_pipe_output.graph_spec

        assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-jsondecode")

        assert mock_pipe_output.graph_spec is original_graph_spec
        mock_event_log.close.assert_called_once()

    def test_swallows_event_log_read_error(self, mocker: MockerFixture) -> None:
        """EventLogReadError (backend infra failure, e.g. DynamoDB throttle) is caught; graph_spec is left unchanged."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mock_event_log = mocker.MagicMock()
        mock_event_log.read_events = mocker.MagicMock(side_effect=EventLogReadError("dynamodb throttled"))
        mocker.patch(
            "pipelex.pipe_run.graph_assembly.make_event_log",
            return_value=mock_event_log,
        )

        mock_pipe_output = mocker.MagicMock()
        original_graph_spec = mock_pipe_output.graph_spec

        assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-read-error")

        assert mock_pipe_output.graph_spec is original_graph_spec
        mock_event_log.close.assert_called_once()

    def test_propagates_unexpected_keyerror(self, mocker: MockerFixture) -> None:
        """Programming bugs (KeyError) propagate — proves tightening from blanket except Exception."""
        mock_config = mocker.patch("pipelex.pipe_run.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mocker.patch(
            "pipelex.pipe_run.graph_assembly.make_event_log",
            side_effect=KeyError("unexpected_key"),
        )

        mock_pipe_output = mocker.MagicMock()

        with pytest.raises(KeyError):
            assemble_graph_on_output(pipe_output=mock_pipe_output, pipeline_run_id="plr-keyerror")
