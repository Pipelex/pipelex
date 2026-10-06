"""Per-call validate seam, mirroring the ``OrchestratorRegistry`` for ``/validate``.

A bundle validator produces a validation verdict for one orchestration mode, the way an
orchestrator runs a pipe for one mode. The seam is generic across orchestrators: the
core ``direct`` plugin contributes the in-process validator (``"direct"``), and an
external orchestrator plugin can contribute a worker-dispatched validator under its own
mode token — which core never names.

Verdict-as-value (not raise): ``validate_bundles`` *returns* the verdict — the valid
report (a ``ValidationReport``) or the invalid ``ErrorReport`` (carrying
``validation_errors``) — and raises only for a no-verdict infra fault (which a host
runtime maps to a 5xx). This is the same valid/invalid pair the API maps to its
200-always ``/validate`` wire, so the verdict contract is backend-independent.

Seam typed at the MTHDS-protocol level (``ValidationReport``), not the concrete
``PipelexValidationReport`` envelope, for two reasons that point the same way: (1) the
concrete report's module reaches the hub, so naming it from this hub-reachable seam
would close an import cycle — the same reason the orchestrator seam returns the leaf
``PipelexPipeRunOutput`` rather than a hub-coupled type; (2) the brand boundary — the
seam is generic across orchestrators (language-standard altitude), so it speaks the
protocol report, and the Pipelex-runtime envelope is the concrete value the validators
produce and the API surfaces. Every Pipelex validator's valid arm is in fact the
canonical ``PipelexValidationReport`` (a ``ValidationReport`` subtype); the API recovers
that precise type at its edge.
"""

from typing import TYPE_CHECKING, Protocol, TypeAlias, runtime_checkable

from mthds.protocol.models import ValidationReport

from pipelex.base_exceptions import ErrorReport
from pipelex.runtime_bridge.orchestration_mode import OrchestrationMode
from pipelex.system.caller_identity import CallerIdentity

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

# The verdict a validator returns: valid arm = the protocol validation report (at runtime
# always the canonical PipelexValidationReport subtype), invalid arm = the structured
# ErrorReport. Bound at runtime (not just under TYPE_CHECKING) so an external validator
# plugin can import it to annotate its own validate_bundles. Both arms are leaf types w.r.t.
# the hub, so this hub-reachable seam stays import-acyclic even with the runtime imports.
BundleValidationVerdict: TypeAlias = ValidationReport | ErrorReport


@runtime_checkable
class BundleValidatorProtocol(Protocol):
    """How ``/validate`` produces a verdict under one orchestration mode.

    A validator plugin registers one of these per ``orchestration_mode`` token it serves
    (``"direct"`` in core; external orchestrator plugins register their own tokens). The
    API resolves the mode and dispatches through the ``BundleValidatorRegistry`` instead
    of branching on a backend. Validation is inherently blocking, so there is no
    ``delivery`` axis here (unlike ``OrchestratorProtocol.run``).

    ``library_dirs`` is host context the in-process arm needs to load the method library;
    a worker-dispatched arm ignores it — its worker loads its own library.

    ``caller_identity`` is who asked for the validation, as the host knows them: the user id
    and the analytics groups it would state on a run. It is required, with ``None`` meaning
    "nobody", so a host cannot forget it — a validation the host serves on a caller's behalf
    must attribute its telemetry to that caller, never to the deployment's configured
    fallback. A worker-dispatched arm carries it to the worker and hands it to the sweep
    there.

    ``graph_pipe_code`` names the pipe the best-effort graph arm dry-runs, resolved the way a
    run resolves its entry pipe, so a bare code or a qualified ref both work. ``None`` keeps
    the default target, the primary blueprint's ``main_pipe``. A host that knows the pipe a
    run of the same request would execute (the ``main_pipe`` of a fetched package's manifest,
    which the bundles themselves may not declare) passes it here so the graph shows that pipe.
    It is required for the same reason as ``caller_identity``: a validator that silently
    dropped it would graph a different pipe than the one the host asked for. A target that
    does not resolve degrades the graph to ``None``, like any other graph-arm failure, and
    never changes the verdict.
    """

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str],
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: "Sequence[Path] | None",
        caller_identity: CallerIdentity | None,
        graph_pipe_code: str | None,
    ) -> BundleValidationVerdict: ...


class BundleValidatorRegistry:
    """Read view over the bundle validators contributed by discovered plugins.

    Keyed by the open ``OrchestrationMode`` token (a ``str``). Built once at boot from
    the registrar's accumulated validators and stored on the hub.
    """

    def __init__(self, validators: dict[OrchestrationMode, BundleValidatorProtocol]):
        self._validators: dict[OrchestrationMode, BundleValidatorProtocol] = dict(validators)

    def get_optional(self, *, mode: OrchestrationMode) -> BundleValidatorProtocol | None:
        return self._validators.get(mode)

    def has(self, *, mode: OrchestrationMode) -> bool:
        return mode in self._validators

    @property
    def modes(self) -> list[OrchestrationMode]:
        return list(self._validators)
