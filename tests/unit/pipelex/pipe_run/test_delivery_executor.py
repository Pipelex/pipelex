import pytest
from pytest_mock import MockerFixture

from pipelex.pipe_run.delivery_assignment import (
    DeliveryAssignment,
    DeliveryStatus,
    StorageTarget,
    WebhookTarget,
)
from pipelex.pipe_run.delivery_executor import DeliveryExecutor
from pipelex.pipe_run.exceptions import StorageDeliveryError, WebhookDeliveryError


@pytest.mark.asyncio(loop_scope="class")
class TestDeliveryExecutor:
    async def test_execute_storage_only(self, mocker: MockerFixture) -> None:
        mock_storage = mocker.AsyncMock()
        mock_storage.store = mocker.AsyncMock(return_value="pipelex-storage://test-key")
        mock_storage.public_url = mocker.Mock(return_value="file:///tmp/results/plr-123")
        mocker.patch("pipelex.pipe_run.delivery_executor.get_storage_provider", return_value=mock_storage)

        mock_output = mocker.MagicMock()
        mock_output.working_memory.smart_dump.return_value = {"root": {}, "aliases": {}}
        mock_output.working_memory.get_optional_main_stuff.return_value = None
        mock_output.graph_spec = None

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(storage=StorageTarget())

        await executor.execute(
            pipe_output=mock_output,
            user_id="test-user",
            pipeline_run_id="plr-123",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

        mock_storage.store.assert_called()
        stored_keys = [call.kwargs["key"] for call in mock_storage.store.call_args_list]
        assert any("test-user/plr-123/results/working_memory.json" in key for key in stored_keys)

    async def test_execute_webhook_only(self, mocker: MockerFixture) -> None:
        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(
            webhooks=[WebhookTarget(url="https://example.com/callback")],
        )

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-456",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["pipeline_run_id"] == "plr-456"
        assert payload["status"] == "COMPLETED"
        assert "result_url" not in payload

    async def test_execute_webhook_with_custom_payload(self, mocker: MockerFixture) -> None:
        mock_client = mocker.AsyncMock()
        mock_response = mocker.MagicMock()
        mock_response.raise_for_status = mocker.Mock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(return_value=mock_response)
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(
            webhooks=[WebhookTarget(url="https://example.com", payload={"custom": "data"})],
        )

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-789",
            delivery_assignment=assignment,
            status=DeliveryStatus.FAILED,
        )

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["status"] == "FAILED"
        assert payload["custom"] == "data"

    async def test_execute_no_storage_on_failure(self, mocker: MockerFixture) -> None:
        """Storage should be skipped when pipe_output is None (failure case)."""
        mock_storage = mocker.AsyncMock()
        mocker.patch("pipelex.pipe_run.delivery_executor.get_storage_provider", return_value=mock_storage)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(storage=StorageTarget())

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-fail",
            delivery_assignment=assignment,
            status=DeliveryStatus.FAILED,
        )

        mock_storage.store.assert_not_called()

    async def test_execute_empty_assignment(self) -> None:
        """Empty assignment should do nothing without errors."""
        executor = DeliveryExecutor()
        assignment = DeliveryAssignment()

        await executor.execute(
            pipe_output=None,
            user_id="test-user",
            pipeline_run_id="plr-noop",
            delivery_assignment=assignment,
            status=DeliveryStatus.COMPLETED,
        )

    async def test_storage_failure_raises(self, mocker: MockerFixture) -> None:
        mock_storage = mocker.AsyncMock()
        mock_storage.store = mocker.AsyncMock(side_effect=Exception("S3 down"))
        mocker.patch("pipelex.pipe_run.delivery_executor.get_storage_provider", return_value=mock_storage)

        mock_output = mocker.MagicMock()
        mock_output.working_memory.smart_dump.return_value = {}
        mock_output.working_memory.get_optional_main_stuff.return_value = None
        mock_output.graph_spec = None

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(storage=StorageTarget())

        with pytest.raises(StorageDeliveryError):
            await executor.execute(
                pipe_output=mock_output,
                user_id="test-user",
                pipeline_run_id="plr-err",
                delivery_assignment=assignment,
                status=DeliveryStatus.COMPLETED,
            )

    async def test_webhook_failure_raises(self, mocker: MockerFixture) -> None:
        import httpx  # noqa: PLC0415

        mock_client = mocker.AsyncMock()
        mock_client.__aenter__ = mocker.AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_client.post = mocker.AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mocker.patch("pipelex.pipe_run.delivery_executor.httpx.AsyncClient", return_value=mock_client)

        executor = DeliveryExecutor()
        assignment = DeliveryAssignment(
            webhooks=[WebhookTarget(url="https://down.example.com")],
        )

        with pytest.raises(WebhookDeliveryError):
            await executor.execute(
                pipe_output=None,
                user_id="test-user",
                pipeline_run_id="plr-err",
                delivery_assignment=assignment,
                status=DeliveryStatus.COMPLETED,
            )
