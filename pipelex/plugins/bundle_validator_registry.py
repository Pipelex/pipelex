"""Per-call validate seam, mirroring the ``OrchestratorRegistry`` for ``/validate``.

A bundle validator produces a validation verdict for one execution mode, the way an
orchestrator runs a pipe for one mode. The seam is generic across orchestrators: the
core ``direct`` plugin contributes the in-process validator (DIRECT), the external
``pipelex-temporal`` plugin contributes the worker-dispatched validator (under both
TEMPORAL_* modes), and a Mistral validator can slot in later — none of which core or a
host runtime names.

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
from pipelex.runtime_bridge.execution_mode import PipelexExecutionMode

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
    """How ``/validate`` produces a verdict under one execution mode.

    A validator plugin registers one of these per ``PipelexExecutionMode`` it serves
    (DIRECT in core; TEMPORAL_* from ``pipelex-temporal``; MISTRAL_NATIVE later). The
    API resolves the mode and dispatches through the ``BundleValidatorRegistry`` instead
    of branching on a backend.

    ``library_dirs`` is host context the in-process arm needs to load the method library;
    a dispatched arm (Temporal) ignores it — its worker loads its own library.
    """

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str],
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: "Sequence[Path] | None",
    ) -> BundleValidationVerdict: ...


class BundleValidatorRegistry:
    """Read view over the bundle validators contributed by discovered plugins.

    Keyed by ``PipelexExecutionMode``. Built once at boot from the registrar's
    accumulated validators and stored on the hub.
    """

    def __init__(self, validators: dict[PipelexExecutionMode, BundleValidatorProtocol]):
        self._validators: dict[PipelexExecutionMode, BundleValidatorProtocol] = dict(validators)

    def get_optional(self, *, mode: PipelexExecutionMode) -> BundleValidatorProtocol | None:
        return self._validators.get(mode)

    def has(self, *, mode: PipelexExecutionMode) -> bool:
        return mode in self._validators

    @property
    def modes(self) -> list[PipelexExecutionMode]:
        return list(self._validators)
