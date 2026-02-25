"""Unit tests for telemetry redaction."""

from pytest_mock import MockerFixture

from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


class TestIsCapturePipeCodesEnabled:
    """Tests for TelemetryManagerAbstract.is_capture_pipe_codes_enabled."""

    def test_returns_false_when_no_telemetry_manager(self) -> None:
        """Test that it returns False when no telemetry manager is configured."""
        TelemetryManagerAbstract.clear_instance()

        result = TelemetryManagerAbstract.is_capture_pipe_codes_enabled()

        assert result is False

    def test_returns_property_value_when_true(self, mocker: MockerFixture) -> None:
        """Test that it returns True when capture_pipe_codes_enabled property is True."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_pipe_codes_enabled = True

        mocker.patch.object(
            TelemetryManagerAbstract,
            "get_instance",
            return_value=mock_instance,
        )

        result = TelemetryManagerAbstract.is_capture_pipe_codes_enabled()

        assert result is True

    def test_returns_property_value_when_false(self, mocker: MockerFixture) -> None:
        """Test that it returns False when capture_pipe_codes_enabled property is False."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_pipe_codes_enabled = False

        mocker.patch.object(
            TelemetryManagerAbstract,
            "get_instance",
            return_value=mock_instance,
        )

        result = TelemetryManagerAbstract.is_capture_pipe_codes_enabled()

        assert result is False
