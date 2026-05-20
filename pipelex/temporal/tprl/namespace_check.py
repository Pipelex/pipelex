"""Worker-startup hard-fail check for the configured custom search attributes.

The five built-in attributes (``PipeCode``, ``PipelineRunId``, ``SessionId``,
``UserId``, ``DomainCode``) are listed in
``pipelex.temporal.config_temporal.BUILTIN_SEARCH_ATTRIBUTES``. The runtime
check operates on the configured subset declared in
``[temporal.search_attributes].attributes``, not on the full built-in set.

Two entry points:

- ``check_required_search_attributes`` — hard-fail audit at worker boot. Raises
  ``SearchAttributeRegistrationError`` (subclass of ``TemporalConfigError``)
  when any *configured* attribute is missing on a reachable namespace; this
  crashes worker boot loudly with the exact registration commands. ``RPCError``
  from the cluster-metadata call stays a soft fail (warn and continue) — the
  namespace was unreachable, not misconfigured. Anything else propagates.
- ``ensure_required_search_attributes_registered`` — auto-register the missing
  attributes. Used by test infrastructure to set up the in-process Temporal
  server before any tests run, and by the ``pipelex setup-temporal-namespace``
  CLI command. Catches ``RPCError(PERMISSION_DENIED)`` on either RPC
  (``ListSearchAttributes`` or ``AddSearchAttributes``) and returns a
  structured ``RegistrationFailure`` instead of raising so the CLI can format
  a fallback runbook for operators whose API key lacks namespace-admin
  permissions. Returns the tuple of newly-registered names (possibly empty,
  for the idempotent "everything already present" no-op) on success so callers
  can report the actual delta instead of the configured-set size.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from temporalio.api.enums.v1 import IndexedValueType
from temporalio.api.operatorservice.v1 import (
    AddSearchAttributesRequest,
    ListSearchAttributesRequest,
)
from temporalio.client import Client as TemporalClient
from temporalio.service import RPCError, RPCStatusCode

from pipelex import log
from pipelex.temporal.exceptions import SearchAttributeRegistrationError

# The Pipelex CLI invocation operators run when their config already points at
# the right server. ``--dry-run`` prints the raw ``temporal`` CLI fallback
# instead of executing.
PIPELEX_SETUP_CLI_COMMAND: Final[str] = "pipelex setup-temporal-namespace"


@dataclass(frozen=True)
class RegistrationFailure:
    """Structured permission-denied outcome from
    ``ensure_required_search_attributes_registered``. The CLI command formats
    this into the fallback runbook so operators whose worker API key lacks
    ``OperatorService.AddSearchAttributes`` permission know which raw
    ``temporal`` / ``tcld`` invocations to run instead.
    """

    namespace: str
    missing: tuple[str, ...]
    rpc_error_message: str


def format_temporal_cli_command(missing: Sequence[str], namespace: str) -> str:
    """Format the exact ``temporal operator search-attribute create`` invocation
    so an operator with raw ``temporal`` CLI access can copy-paste it.
    """
    parts = [
        "temporal operator search-attribute create",
        f"  --namespace {namespace}",
    ]
    for name in missing:
        parts.append(f"  --name {name} --type Keyword")
    return " \\\n".join(parts)


def format_tcld_cli_command(missing: Sequence[str], namespace: str) -> str:
    """Format the Temporal Cloud ``tcld`` invocation a namespace admin runs
    when the worker API key lacks ``OperatorService.AddSearchAttributes``
    permission. Used both as a hint in the dry-run output and as part of the
    permission-denied fallback runbook.
    """
    attribute_flags = " ".join(f"--search-attribute {name}=Keyword" for name in missing)
    return f"tcld namespace search-attributes add --namespace {namespace} {attribute_flags}"


async def check_required_search_attributes(
    temporal_client: TemporalClient,
    namespace: str,
    configured_attributes: Sequence[str],
) -> None:
    """Hard-fail at worker boot if any configured custom search attribute is
    missing on a reachable namespace.

    Failure model:

    - All configured attributes present → silent.
    - Some missing on a reachable namespace → raise
      ``SearchAttributeRegistrationError`` with both the ``pipelex
      setup-temporal-namespace`` invocation and the equivalent raw ``temporal
      operator search-attribute create`` command in the message.
    - ``RPCError`` from the operator service (namespace unreachable, transient
      cluster issue) → log a warning, continue. Fast-failing here would block
      every worker boot during a control-plane outage; the cluster will reject
      workflow starts that reference unregistered attributes anyway.
    - Any other exception → propagates and crashes worker boot.

    Args:
        temporal_client: The client used to talk to the operator service.
        namespace: Namespace to inspect; usually ``temporal_client.namespace``.
        configured_attributes: The subset of attribute names the worker is
            configured to populate. Pass an empty sequence to skip the check
            entirely (the caller normally does this when
            ``[temporal.search_attributes].enabled = false``).
    """
    if not configured_attributes:
        return
    try:
        response = await temporal_client.operator_service.list_search_attributes(
            ListSearchAttributesRequest(namespace=namespace),
        )
    except RPCError as exc:
        log.warning(
            f"Temporal search-attribute check could not reach namespace '{namespace}' "
            f"(RPCError: {exc}). Worker boot continues; workflow starts will fail at "
            f"dispatch time if the configured attributes are not registered."
        )
        return

    present = set(response.custom_attributes.keys())
    missing = tuple(name for name in configured_attributes if name not in present)
    if not missing:
        return

    temporal_cli_command = format_temporal_cli_command(missing, namespace=namespace)
    msg = (
        f"Temporal namespace '{namespace}' is missing required custom search attributes: "
        f"{list(missing)}. Workflow starts that reference these attributes are rejected "
        f"by the cluster, so worker boot is aborted. Register them with either:\n\n"
        f"  {PIPELEX_SETUP_CLI_COMMAND}\n\n"
        f"or directly via the Temporal CLI:\n\n"
        f"{temporal_cli_command}\n"
    )
    raise SearchAttributeRegistrationError(msg)


async def ensure_required_search_attributes_registered(
    temporal_client: TemporalClient,
    namespace: str,
    configured_attributes: Sequence[str],
) -> RegistrationFailure | tuple[str, ...]:
    """Register any missing configured search attributes as Keyword.

    Idempotent: calls ``ListSearchAttributes`` first and only adds the ones
    that are absent. Used by test infrastructure to set up the in-process
    Temporal server and by the ``pipelex setup-temporal-namespace`` CLI
    command.

    Returns the tuple of newly-registered attribute names on success — an
    empty tuple in the idempotent "everything already registered" no-op case,
    otherwise the names that were just added. Returns a ``RegistrationFailure``
    when the namespace is reachable but the client's API key lacks read
    (``ListSearchAttributes``) or write (``AddSearchAttributes``) permission;
    the CLI command formats it into the fallback runbook. Other ``RPCError``
    codes (``UNAVAILABLE``, ``NOT_FOUND``) propagate.

    Args:
        temporal_client: The client used to talk to the operator service.
        namespace: Namespace to register against.
        configured_attributes: Subset of attribute names to ensure are
            registered. Pass ``BUILTIN_SEARCH_ATTRIBUTES`` for the full set.
    """
    if not configured_attributes:
        return ()
    try:
        response = await temporal_client.operator_service.list_search_attributes(
            ListSearchAttributesRequest(namespace=namespace),
        )
    except RPCError as list_exc:
        if list_exc.status == RPCStatusCode.PERMISSION_DENIED:
            # Without read access we cannot compute the actual missing set, so
            # surface the full configured set as the operator's work item.
            return RegistrationFailure(
                namespace=namespace,
                missing=tuple(configured_attributes),
                rpc_error_message=str(list_exc),
            )
        raise
    present = set(response.custom_attributes.keys())
    missing = tuple(name for name in configured_attributes if name not in present)
    if not missing:
        return ()

    try:
        await temporal_client.operator_service.add_search_attributes(
            AddSearchAttributesRequest(
                namespace=namespace,
                search_attributes=dict.fromkeys(missing, IndexedValueType.INDEXED_VALUE_TYPE_KEYWORD),
            ),
        )
    except RPCError as add_exc:
        if add_exc.status == RPCStatusCode.PERMISSION_DENIED:
            return RegistrationFailure(
                namespace=namespace,
                missing=missing,
                rpc_error_message=str(add_exc),
            )
        raise
    return missing
