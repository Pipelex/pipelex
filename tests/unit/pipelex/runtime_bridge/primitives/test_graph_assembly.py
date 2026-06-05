import pytest
from pytest_mock import MockerFixture

from pipelex.runtime_bridge.primitives.graph_assembly import assemble_graph_for_pipeline_run
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.exceptions import EventLogReadError


class TestAssembleGraphForPipelineRun:
    @pytest.mark.asyncio
    async def test_returns_none_when_tracing_disabled(self, mocker: MockerFixture) -> None:
        mock_config = mocker.patch("pipelex.runtime_bridge.primitives.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = False

        mock_make_event_log = mocker.patch("pipelex.runtime_bridge.primitives.graph_assembly.make_event_log")

        result = await assemble_graph_for_pipeline_run(pipeline_run_id="plr-disabled")

        assert result is None
        mock_make_event_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_degrades_to_none_on_oserror(self, mocker: MockerFixture) -> None:
        mock_config = mocker.patch("pipelex.runtime_bridge.primitives.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mock_event_log = mocker.MagicMock()
        mock_event_log.read_events = mocker.MagicMock(side_effect=OSError("file vanished"))
        mocker.patch(
            "pipelex.runtime_bridge.primitives.graph_assembly.make_event_log",
            return_value=mock_event_log,
        )

        result = await assemble_graph_for_pipeline_run(pipeline_run_id="plr-oserror")

        assert result is None
        mock_event_log.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_degrades_to_none_on_missing_dependency(self, mocker: MockerFixture) -> None:
        mock_config = mocker.patch("pipelex.runtime_bridge.primitives.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mocker.patch(
            "pipelex.runtime_bridge.primitives.graph_assembly.make_event_log",
            side_effect=MissingDependencyError(dependency_name="boto3", extra_name="aws"),
        )

        result = await assemble_graph_for_pipeline_run(pipeline_run_id="plr-missing-dep")

        assert result is None

    @pytest.mark.asyncio
    async def test_degrades_to_none_on_event_log_read_error(self, mocker: MockerFixture) -> None:
        # A backend infra failure (e.g. DynamoDB throttle) surfaces as EventLogReadError;
        # graph assembly must degrade to None rather than fail the pipeline run.
        mock_config = mocker.patch("pipelex.runtime_bridge.primitives.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mock_event_log = mocker.MagicMock()
        mock_event_log.read_events = mocker.MagicMock(side_effect=EventLogReadError("dynamodb throttled"))
        mocker.patch(
            "pipelex.runtime_bridge.primitives.graph_assembly.make_event_log",
            return_value=mock_event_log,
        )

        result = await assemble_graph_for_pipeline_run(pipeline_run_id="plr-read-error")

        assert result is None
        mock_event_log.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_propagates_unexpected_keyerror(self, mocker: MockerFixture) -> None:
        # Programming bugs (KeyError) propagate — proves tightening from the former blanket except Exception.
        mock_config = mocker.patch("pipelex.runtime_bridge.primitives.graph_assembly.get_config")
        mock_config.return_value.pipelex.tracing_config.is_enabled = True

        mocker.patch(
            "pipelex.runtime_bridge.primitives.graph_assembly.make_event_log",
            side_effect=KeyError("unexpected_key"),
        )

        with pytest.raises(KeyError):
            await assemble_graph_for_pipeline_run(pipeline_run_id="plr-keyerror")
