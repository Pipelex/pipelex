"""Unit tests for telemetry redaction and run ID generation."""

from pytest_mock import MockerFixture

from pipelex.pipeline.run_id_factory import make_pipe_run_id, make_pipeline_run_id
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract


class TestMakePipelineRunId:
    """Tests for make_pipeline_run_id with capture_pipe_codes_enabled settings."""

    def test_includes_pipe_code_when_capture_enabled(self, mocker: MockerFixture) -> None:
        """Test that pipe code is included when capture_pipe_codes_enabled is True."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_pipe_codes_enabled = True
        mocker.patch.object(TelemetryManagerAbstract, "get_instance", return_value=mock_instance)

        result = make_pipeline_run_id("my_pipe")

        assert result.startswith("my_pipe_")
        assert len(result) == len("my_pipe_") + 5  # pipe_code + underscore + 5 char short_id

    def test_excludes_pipe_code_when_capture_disabled(self, mocker: MockerFixture) -> None:
        """Test that pipe code is excluded when capture_pipe_codes_enabled is False."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_pipe_codes_enabled = False
        mocker.patch.object(TelemetryManagerAbstract, "get_instance", return_value=mock_instance)

        result = make_pipeline_run_id("my_pipe")

        # Should be a full shortuuid (22 chars), no pipe code
        assert len(result) == 22
        assert "_" not in result

    def test_returns_full_uuid_when_pipe_code_is_none(self, mocker: MockerFixture) -> None:
        """Test that full uuid is returned when pipe_code is None."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_pipe_codes_enabled = True
        mocker.patch.object(TelemetryManagerAbstract, "get_instance", return_value=mock_instance)

        result = make_pipeline_run_id(None)

        assert len(result) == 22
        assert "_" not in result

    def test_excludes_pipe_code_when_no_telemetry_manager(self) -> None:
        """Test that pipe code is excluded when no telemetry manager exists."""
        TelemetryManagerAbstract.clear_instance()

        result = make_pipeline_run_id("my_pipe")

        # Should be a full shortuuid since is_capture_pipe_codes_enabled returns False
        assert len(result) == 22
        assert "_" not in result


class TestMakePipeRunId:
    """Tests for make_pipe_run_id with capture_pipe_codes_enabled settings."""

    def test_includes_pipe_code_when_capture_enabled(self, mocker: MockerFixture) -> None:
        """Test that pipe code is included when capture_pipe_codes_enabled is True."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_pipe_codes_enabled = True
        mocker.patch.object(TelemetryManagerAbstract, "get_instance", return_value=mock_instance)

        result = make_pipe_run_id("my_pipe")

        assert result.startswith("my_pipe_")
        assert len(result) == len("my_pipe_") + 5

    def test_excludes_pipe_code_when_capture_disabled(self, mocker: MockerFixture) -> None:
        """Test that pipe code is excluded when capture_pipe_codes_enabled is False."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_pipe_codes_enabled = False
        mocker.patch.object(TelemetryManagerAbstract, "get_instance", return_value=mock_instance)

        result = make_pipe_run_id("my_pipe")

        # Should be a full shortuuid (22 chars), no pipe code
        assert len(result) == 22
        assert "_" not in result


class TestIsCaptureContentEnabled:
    """Tests for TelemetryManagerAbstract.is_capture_content_enabled."""

    def test_returns_false_when_no_telemetry_manager(self) -> None:
        """Test that it returns False when no telemetry manager is configured."""
        TelemetryManagerAbstract.clear_instance()

        result = TelemetryManagerAbstract.is_capture_content_enabled()

        assert result is False

    def test_returns_property_value_when_true(self, mocker: MockerFixture) -> None:
        """Test that it returns True when capture_content_enabled property is True."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_content_enabled = True

        mocker.patch.object(
            TelemetryManagerAbstract,
            "get_instance",
            return_value=mock_instance,
        )

        result = TelemetryManagerAbstract.is_capture_content_enabled()

        assert result is True

    def test_returns_property_value_when_false(self, mocker: MockerFixture) -> None:
        """Test that it returns False when capture_content_enabled property is False."""
        mock_instance = mocker.MagicMock()
        mock_instance.capture_content_enabled = False

        mocker.patch.object(
            TelemetryManagerAbstract,
            "get_instance",
            return_value=mock_instance,
        )

        result = TelemetryManagerAbstract.is_capture_content_enabled()

        assert result is False


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
