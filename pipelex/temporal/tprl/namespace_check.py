"""Worker-startup soft-fail check for the required custom search attributes.

The five attributes (``PipeCode``, ``PipelineRunId``, ``SessionId``, ``UserId``,
``DomainCode``) must be registered on the Temporal namespace before workflow
starts populate them — otherwise the cluster's ``StartWorkflowExecution`` RPC
rejects every workflow that sets them.

Two entry points:

- ``check_required_search_attributes`` — soft-fail audit at worker boot. Warns if
  any are missing; safe to call from production code. ``RPCError`` from the
  cluster-metadata call does not block worker boot. Anything other than
  ``RPCError`` propagates — it is a real bug, not a degraded-dashboard concern.
- ``ensure_required_search_attributes_registered`` — auto-register the missing
  attributes. Used by test infrastructure to set up the in-process Temporal
  server before any tests run. Not for production: production clusters expect
  the namespace operator to register attributes explicitly.
"""

from collections.abc import Sequence

from temporalio.api.enums.v1 import IndexedValueType
from temporalio.api.operatorservice.v1 import (
    AddSearchAttributesRequest,
    ListSearchAttributesRequest,
)
from temporalio.client import Client as TemporalClient
from temporalio.service import RPCError

from pipelex import log

REQUIRED_SEARCH_ATTRIBUTES: tuple[str, ...] = (
    "PipeCode",
    "PipelineRunId",
    "SessionId",
    "UserId",
    "DomainCode",
)


def _format_registration_command(missing: Sequence[str], namespace: str) -> str:
    """Format the exact ``temporal operator search-attribute create`` invocation
    so the operator can copy-paste it from the warning log.
    """
    parts = [
        "temporal operator search-attribute create",
        f"  --namespace {namespace}",
    ]
    for name in missing:
        parts.append(f"  --name {name} --type Keyword")
    return " \\\n".join(parts)


async def check_required_search_attributes(
    temporal_client: TemporalClient,
    namespace: str,
) -> None:
    """Warn (soft-fail) if any of the required custom search attributes are missing.

    - All attributes present → silent.
    - Some missing → log a warning naming the missing attributes and the exact
      registration command.
    - ``RPCError`` from the operator service → log a warning, continue.

    Other exceptions propagate; they indicate a real bug rather than a
    degraded-dashboard concern.
    """
    try:
        response = await temporal_client.operator_service.list_search_attributes(
            ListSearchAttributesRequest(namespace=namespace),
        )
    except RPCError as exc:
        log.warning(
            f"Temporal search-attribute check could not reach namespace '{namespace}' "
            f"(RPCError: {exc}). Worker boot continues; dashboard filtering by "
            f"PipeCode / PipelineRunId / SessionId / UserId / DomainCode may be degraded."
        )
        return

    present = set(response.custom_attributes.keys())
    missing = [name for name in REQUIRED_SEARCH_ATTRIBUTES if name not in present]
    if not missing:
        return

    registration_command = _format_registration_command(missing, namespace=namespace)
    log.warning(
        f"Temporal namespace '{namespace}' is missing required custom search attributes: "
        f"{missing}. Workflows still run, but the Pipelex dashboard view is degraded "
        f"until they are registered. Register with:\n\n{registration_command}\n"
    )


async def ensure_required_search_attributes_registered(
    temporal_client: TemporalClient,
    namespace: str,
) -> None:
    """Register any missing required search attributes as Keyword.

    Idempotent: calls ``ListSearchAttributes`` first and only adds the ones that
    are absent. Used by test infrastructure to set up the in-process Temporal
    server. Production clusters should register attributes via the namespace
    operator, not via this helper.

    ``RPCError`` propagates so the caller can decide what to do (test
    infrastructure typically wants to fail loudly; production code should not
    use this function at all).
    """
    response = await temporal_client.operator_service.list_search_attributes(
        ListSearchAttributesRequest(namespace=namespace),
    )
    present = set(response.custom_attributes.keys())
    missing = [name for name in REQUIRED_SEARCH_ATTRIBUTES if name not in present]
    if not missing:
        return

    await temporal_client.operator_service.add_search_attributes(
        AddSearchAttributesRequest(
            namespace=namespace,
            search_attributes=dict.fromkeys(missing, IndexedValueType.INDEXED_VALUE_TYPE_KEYWORD),
        ),
    )
