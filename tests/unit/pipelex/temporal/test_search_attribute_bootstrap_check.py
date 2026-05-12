"""Unit tests for the worker-startup hard-fail check of configured custom search attributes.

Phase 6 contract:

- All configured attributes present → no warning, no exception.
- Some configured attributes missing on a reachable namespace → raise
  ``SearchAttributeRegistrationError`` with both the ``pipelex
  setup-temporal-namespace`` invocation and the equivalent raw ``temporal
  operator search-attribute create`` command in the message.
- ``RPCError`` from the operator service → worker boot continues, soft-fail
  warning logged.
- Any other exception → propagates and crashes the worker (real bug).
- Empty ``configured_attributes`` (``[temporal.search_attributes].enabled =
  false`` short-circuits to this) → check is skipped entirely; the operator
  service is never called.
- Configured subset → only the subset is checked; missing built-ins outside
  the subset don't trigger the error.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio.service import RPCError, RPCStatusCode

from pipelex.temporal.config_temporal import BUILTIN_SEARCH_ATTRIBUTES
from pipelex.temporal.exceptions import SearchAttributeRegistrationError
from pipelex.temporal.tprl.namespace_check import check_required_search_attributes


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
    async def test_all_configured_attributes_present_is_silent(self, mocker: MockerFixture) -> None:
        client = _make_temporal_client_stub(
            mocker,
            custom_attributes={name: object() for name in BUILTIN_SEARCH_ATTRIBUTES},
        )
        warning_mock = mocker.patch("pipelex.temporal.tprl.namespace_check.log.warning")

        await check_required_search_attributes(
            temporal_client=client,
            namespace="default",
            configured_attributes=BUILTIN_SEARCH_ATTRIBUTES,
        )

        warning_mock.assert_not_called()

    async def test_some_configured_attributes_missing_raises_with_both_commands(self, mocker: MockerFixture) -> None:
        # Only two of the five present; three are missing.
        client = _make_temporal_client_stub(
            mocker,
            custom_attributes={"PipeCode": object(), "PipelineRunId": object()},
        )

        with pytest.raises(SearchAttributeRegistrationError) as exc_info:
            await check_required_search_attributes(
                temporal_client=client,
                namespace="default",
                configured_attributes=BUILTIN_SEARCH_ATTRIBUTES,
            )

        message = str(exc_info.value)
        # The missing names appear in the message.
        assert "SessionId" in message
        assert "UserId" in message
        assert "DomainCode" in message
        # The Pipelex CLI invocation is part of the actionable hint.
        assert "pipelex setup-temporal-namespace" in message
        # The equivalent raw Temporal CLI command is also embedded verbatim.
        assert "temporal operator search-attribute create" in message
        assert "--namespace default" in message
        assert "--name SessionId --type Keyword" in message
        assert "--name UserId --type Keyword" in message
        assert "--name DomainCode --type Keyword" in message

    async def test_rpc_error_soft_fails_and_logs_warning(self, mocker: MockerFixture) -> None:
        rpc_error = RPCError("namespace not reachable", RPCStatusCode.UNAVAILABLE, raw_grpc_status=b"")
        client = _make_temporal_client_stub(mocker, custom_attributes=rpc_error)
        warning_mock = mocker.patch("pipelex.temporal.tprl.namespace_check.log.warning")

        # Must NOT raise — soft-fail when the cluster control plane is unreachable.
        await check_required_search_attributes(
            temporal_client=client,
            namespace="default",
            configured_attributes=BUILTIN_SEARCH_ATTRIBUTES,
        )

        warning_mock.assert_called_once()
        assert "RPCError" in warning_mock.call_args.args[0]

    async def test_non_rpc_error_propagates_and_crashes(self, mocker: MockerFixture) -> None:
        """Anything other than ``RPCError`` is a real bug — must propagate."""
        client = _make_temporal_client_stub(mocker, custom_attributes=RuntimeError("unexpected bug"))

        with pytest.raises(RuntimeError, match="unexpected bug"):
            await check_required_search_attributes(
                temporal_client=client,
                namespace="default",
                configured_attributes=BUILTIN_SEARCH_ATTRIBUTES,
            )

    async def test_configured_subset_ignores_missing_attributes_outside_the_subset(self, mocker: MockerFixture) -> None:
        """When the configured subset is ``["PipeCode", "DomainCode"]`` and both
        of those are registered, the check must pass even though the three other
        built-ins are missing — they're not in the subset.
        """
        client = _make_temporal_client_stub(
            mocker,
            custom_attributes={"PipeCode": object(), "DomainCode": object()},
        )

        await check_required_search_attributes(
            temporal_client=client,
            namespace="default",
            configured_attributes=["PipeCode", "DomainCode"],
        )

    async def test_empty_configured_attributes_skips_the_check_entirely(self, mocker: MockerFixture) -> None:
        """When ``[temporal.search_attributes].enabled = false`` is wired
        through, callers pass an empty configured subset. The operator service
        must not be called at all.
        """
        client = _make_temporal_client_stub(mocker, custom_attributes={})
        warning_mock = mocker.patch("pipelex.temporal.tprl.namespace_check.log.warning")

        await check_required_search_attributes(
            temporal_client=client,
            namespace="default",
            configured_attributes=[],
        )

        client.operator_service.list_search_attributes.assert_not_called()
        warning_mock.assert_not_called()
