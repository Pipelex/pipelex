"""Unit tests for the worker-startup soft-fail check of required custom search attributes.

The five required attributes (``PipeCode``, ``PipelineRunId``, ``SessionId``,
``UserId``, ``DomainCode``) are listed in ``namespace_check.REQUIRED_SEARCH_ATTRIBUTES``.

Failure-mode contract:

- All present → no warning logged.
- Some missing → warning logged with the exact registration command and missing names.
- ``RPCError`` from operator service → worker boot continues, soft-fail warning logged.
- Any other exception → propagates and crashes the worker (real bug, not a degraded-dashboard concern).
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio.service import RPCError, RPCStatusCode

from pipelex.temporal.tprl.namespace_check import REQUIRED_SEARCH_ATTRIBUTES, check_required_search_attributes


def _make_temporal_client_stub(mocker: MockerFixture, custom_attributes: dict[str, Any] | Exception) -> Any:
    """Stub a temporal client whose ``operator_service.list_search_attributes``
    returns the given attributes (or raises the given exception).
    """
    client = mocker.MagicMock()
    response = mocker.MagicMock()
    response.custom_attributes = custom_attributes if not isinstance(custom_attributes, Exception) else {}
    if isinstance(custom_attributes, Exception):
        client.operator_service.list_search_attributes = mocker.AsyncMock(side_effect=custom_attributes)
    else:
        client.operator_service.list_search_attributes = mocker.AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio(loop_scope="class")
class TestSearchAttributeBootstrapCheck:
    async def test_all_attributes_present_logs_no_warning(self, mocker: MockerFixture) -> None:
        client = _make_temporal_client_stub(
            mocker,
            custom_attributes={name: object() for name in REQUIRED_SEARCH_ATTRIBUTES},
        )
        warning_mock = mocker.patch("pipelex.temporal.tprl.namespace_check.log.warning")

        await check_required_search_attributes(temporal_client=client, namespace="default")

        warning_mock.assert_not_called()

    async def test_some_attributes_missing_logs_warning_with_registration_command(self, mocker: MockerFixture) -> None:
        # Only two of the five present; the other three are missing.
        client = _make_temporal_client_stub(
            mocker,
            custom_attributes={"PipeCode": object(), "PipelineRunId": object()},
        )
        warning_mock = mocker.patch("pipelex.temporal.tprl.namespace_check.log.warning")

        await check_required_search_attributes(temporal_client=client, namespace="default")

        warning_mock.assert_called_once()
        warning_text = warning_mock.call_args.args[0]
        # The missing names appear in the warning.
        assert "SessionId" in warning_text
        assert "UserId" in warning_text
        assert "DomainCode" in warning_text
        # The registration command is included verbatim and references the namespace.
        assert "temporal operator search-attribute create" in warning_text
        assert "--namespace default" in warning_text
        # Each missing attribute appears with its --name flag.
        assert "--name SessionId --type Keyword" in warning_text
        assert "--name UserId --type Keyword" in warning_text
        assert "--name DomainCode --type Keyword" in warning_text

    async def test_rpc_error_soft_fails_and_logs_warning(self, mocker: MockerFixture) -> None:
        rpc_error = RPCError("namespace not reachable", RPCStatusCode.UNAVAILABLE, raw_grpc_status=b"")
        client = _make_temporal_client_stub(mocker, custom_attributes=rpc_error)
        warning_mock = mocker.patch("pipelex.temporal.tprl.namespace_check.log.warning")

        # Must NOT raise — soft-fail by design.
        await check_required_search_attributes(temporal_client=client, namespace="default")

        warning_mock.assert_called_once()
        assert "RPCError" in warning_mock.call_args.args[0]

    async def test_non_rpc_error_propagates_and_crashes(self, mocker: MockerFixture) -> None:
        """Anything other than ``RPCError`` is a real bug — must propagate."""
        client = _make_temporal_client_stub(mocker, custom_attributes=RuntimeError("unexpected bug"))

        with pytest.raises(RuntimeError, match="unexpected bug"):
            await check_required_search_attributes(temporal_client=client, namespace="default")
