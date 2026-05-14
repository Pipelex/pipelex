import pytest
from pytest_mock import MockerFixture

from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_run.dry_run import DryRunStatus, dry_run_pipe, dry_run_pipes


class TestDryRun:
    """Tests for dry_run_pipe and dry_run_pipes status reporting."""

    @pytest.mark.asyncio
    async def test_dry_run_pipe_with_unresolved_dependency_returns_skipped(self, mocker: MockerFixture) -> None:
        """A pipe that raises PipeNotFoundError should be reported as SKIPPED, not SUCCESS."""
        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "test_pipe"
        mock_pipe.collect_signature_refs.return_value = set()
        mock_pipe.needed_inputs.side_effect = PipeNotFoundError("dep->some_domain.some_pipe not found")

        result = await dry_run_pipe(mock_pipe)

        assert result.status == DryRunStatus.SKIPPED
        assert result.error_message is not None
        assert "unresolved dependency" in result.error_message

    @pytest.mark.asyncio
    async def test_dry_run_pipe_with_unresolved_dependency_is_not_success(self, mocker: MockerFixture) -> None:
        """Ensure skipped pipes are NOT counted as successful."""
        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "test_pipe"
        mock_pipe.collect_signature_refs.return_value = set()
        mock_pipe.needed_inputs.side_effect = PipeNotFoundError("dep->some_domain.some_pipe not found")

        result = await dry_run_pipe(mock_pipe)

        assert result.status != DryRunStatus.SUCCESS
        assert not result.status.is_success

    @pytest.mark.asyncio
    async def test_dry_run_pipes_counts_skipped_separately(self, mocker: MockerFixture) -> None:
        """Skipped pipes must not inflate the success count in dry_run_pipes."""
        mock_successful_pipe = mocker.MagicMock()
        mock_successful_pipe.code = "successful_pipe"
        mock_successful_pipe.pipe_ref = "test_domain.successful_pipe"
        mock_successful_pipe.collect_signature_refs.return_value = set()
        mock_successful_pipe.needed_inputs.return_value = mocker.MagicMock(named_stuff_specs=[])
        mock_successful_pipe.validate_with_libraries.return_value = None
        mock_successful_pipe.run_pipe = mocker.AsyncMock(return_value=None)

        mock_skipped_pipe = mocker.MagicMock()
        mock_skipped_pipe.code = "skipped_pipe"
        mock_skipped_pipe.pipe_ref = "test_domain.skipped_pipe"
        mock_skipped_pipe.collect_signature_refs.return_value = set()
        mock_skipped_pipe.needed_inputs.side_effect = PipeNotFoundError("dep->domain.pipe not found")

        results = await dry_run_pipes(
            pipes=[mock_successful_pipe, mock_skipped_pipe],
            raise_on_failure=False,
        )

        assert results["test_domain.successful_pipe"].status == DryRunStatus.SUCCESS
        assert results["test_domain.skipped_pipe"].status == DryRunStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_dry_run_pipe_skipped_is_not_failure(self, mocker: MockerFixture) -> None:
        """A skipped pipe should not be treated as a failure either."""
        mock_pipe = mocker.MagicMock()
        mock_pipe.code = "test_pipe"
        mock_pipe.collect_signature_refs.return_value = set()
        mock_pipe.needed_inputs.side_effect = PipeNotFoundError("missing dep")

        result = await dry_run_pipe(mock_pipe)

        assert result.status == DryRunStatus.SKIPPED
        assert not result.status.is_failure
