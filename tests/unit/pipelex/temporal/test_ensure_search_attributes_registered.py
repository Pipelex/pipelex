"""Unit tests for ``ensure_required_search_attributes_registered``.

The helper is used both by the test conftest (in-process server bootstrap) and
by the ``pipelex setup-temporal-namespace`` CLI command. It MUST:

- Return the tuple of newly-registered attribute names on success.
- Return an empty tuple on the idempotent "everything already registered" no-op
  so callers can report the actual delta instead of the configured-set size.
- Return ``RegistrationFailure`` on ``RPCError(PERMISSION_DENIED)`` from EITHER
  RPC (``ListSearchAttributes`` or ``AddSearchAttributes``) so the CLI can
  print the fallback runbook without leaking a "could not reach" message that
  misdirects the operator.
- Propagate any other ``RPCError`` so the CLI can frame transient cluster
  errors distinctly.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio.service import RPCError, RPCStatusCode

from pipelex.temporal.tprl.namespace_check import RegistrationFailure, ensure_required_search_attributes_registered


def _make_client_stub(
    mocker: MockerFixture,
    *,
    list_response: dict[str, Any] | Exception,
    add_side_effect: Exception | None = None,
) -> Any:
    """Build a fake Temporal client whose ``operator_service`` calls behave as configured."""
    client = mocker.MagicMock()
    if isinstance(list_response, Exception):
        client.operator_service.list_search_attributes = mocker.AsyncMock(side_effect=list_response)
    else:
        response = mocker.MagicMock()
        response.custom_attributes = list_response
        client.operator_service.list_search_attributes = mocker.AsyncMock(return_value=response)
    if add_side_effect is not None:
        client.operator_service.add_search_attributes = mocker.AsyncMock(side_effect=add_side_effect)
    else:
        client.operator_service.add_search_attributes = mocker.AsyncMock()
    return client


@pytest.mark.asyncio(loop_scope="class")
class TestEnsureSearchAttributesRegistered:
    async def test_returns_newly_registered_tuple_when_some_missing(self, mocker: MockerFixture) -> None:
        # Two of the five are already there; three need to be added.
        client = _make_client_stub(
            mocker,
            list_response={"PipeCode": object(), "PipelineRunId": object()},
        )

        outcome = await ensure_required_search_attributes_registered(
            temporal_client=client,
            namespace="default",
            configured_attributes=["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"],
        )

        assert outcome == ("SessionId", "UserId", "DomainCode")
        client.operator_service.add_search_attributes.assert_awaited_once()

    async def test_returns_empty_tuple_when_everything_already_present(self, mocker: MockerFixture) -> None:
        """Idempotent no-op: the CLI must be able to tell this apart from a
        real registration so operators don't see a misleading "Registered 5".
        """
        client = _make_client_stub(
            mocker,
            list_response={name: object() for name in ("PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode")},
        )

        outcome = await ensure_required_search_attributes_registered(
            temporal_client=client,
            namespace="default",
            configured_attributes=["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"],
        )

        assert outcome == ()
        client.operator_service.add_search_attributes.assert_not_called()

    async def test_returns_empty_tuple_when_configured_set_is_empty(self, mocker: MockerFixture) -> None:
        """When ``[temporal.search_attributes].enabled = false`` is wired
        through, callers pass an empty configured subset. The helper must
        short-circuit before touching the operator service.
        """
        client = _make_client_stub(mocker, list_response={})

        outcome = await ensure_required_search_attributes_registered(
            temporal_client=client,
            namespace="default",
            configured_attributes=[],
        )

        assert outcome == ()
        client.operator_service.list_search_attributes.assert_not_called()
        client.operator_service.add_search_attributes.assert_not_called()

    async def test_permission_denied_on_list_returns_registration_failure(self, mocker: MockerFixture) -> None:
        """If the API key cannot ``ListSearchAttributes`` the helper must NOT
        leak a raw ``RPCError`` (which the CLI frames as "could not reach"
        — wrong direction); it must return a ``RegistrationFailure`` with
        the full configured set so the operator's fallback runbook contains
        the right list. Regression for the bug where only the ADD call had
        PERMISSION_DENIED handling.
        """
        list_exc = RPCError("permission denied", RPCStatusCode.PERMISSION_DENIED, raw_grpc_status=b"")
        client = _make_client_stub(mocker, list_response=list_exc)

        outcome = await ensure_required_search_attributes_registered(
            temporal_client=client,
            namespace="ns1",
            configured_attributes=["PipeCode", "PipelineRunId", "SessionId"],
        )

        assert isinstance(outcome, RegistrationFailure)
        assert outcome.namespace == "ns1"
        # Without read access we cannot compute the actual missing set; surface
        # the whole configured list so the operator's runbook contains everything.
        assert outcome.missing == ("PipeCode", "PipelineRunId", "SessionId")
        assert "permission denied" in outcome.rpc_error_message
        # The ADD RPC must never be attempted in this branch.
        client.operator_service.add_search_attributes.assert_not_called()

    async def test_permission_denied_on_add_returns_registration_failure(self, mocker: MockerFixture) -> None:
        add_exc = RPCError("permission denied", RPCStatusCode.PERMISSION_DENIED, raw_grpc_status=b"")
        client = _make_client_stub(
            mocker,
            list_response={"PipeCode": object()},
            add_side_effect=add_exc,
        )

        outcome = await ensure_required_search_attributes_registered(
            temporal_client=client,
            namespace="ns1",
            configured_attributes=["PipeCode", "PipelineRunId", "SessionId"],
        )

        assert isinstance(outcome, RegistrationFailure)
        assert outcome.namespace == "ns1"
        # Only the actually-missing names are surfaced — read access succeeded.
        assert outcome.missing == ("PipelineRunId", "SessionId")
        assert "permission denied" in outcome.rpc_error_message

    async def test_non_permission_denied_rpc_error_on_list_propagates(self, mocker: MockerFixture) -> None:
        """``UNAVAILABLE`` / ``NOT_FOUND`` etc. must propagate so the CLI can
        frame them as connectivity / configuration issues rather than as
        permission failures.
        """
        list_exc = RPCError("namespace not reachable", RPCStatusCode.UNAVAILABLE, raw_grpc_status=b"")
        client = _make_client_stub(mocker, list_response=list_exc)

        with pytest.raises(RPCError) as exc_info:
            await ensure_required_search_attributes_registered(
                temporal_client=client,
                namespace="ns1",
                configured_attributes=["PipeCode"],
            )

        assert exc_info.value.status == RPCStatusCode.UNAVAILABLE
