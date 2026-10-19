"""Per-call validate seam, mirroring the ``OrchestratorRegistry`` for ``/validate``.

A bundle validator produces a validation verdict for one orchestration mode, the way an
orchestrator runs a pipe for one mode. The seam is generic across orchestrators: the
core ``direct`` plugin contributes the in-process validator (``"direct"``), and an
external orchestrator plugin can contribute a worker-dispatched validator under its own
mode token — which core never names.

Verdict-as-value (not raise): ``validate_bundles`` *returns* the verdict — the valid
report (a ``ValidationReport``) or the invalid ``BundleValidationFailure`` (the refusal's
problem in the operator's view, with its ``validation_errors``) — and raises only for a
no-verdict fault, which a host runtime answers with that fault's problem. This is the same valid/invalid pair the API maps to its
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

from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, runtime_checkable

from mthds.protocol.models import ValidationReport

from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.runtime_bridge.orchestration_mode import OrchestrationMode
from pipelex.system.caller_identity import CallerIdentity

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

# The verdict a validator returns: valid arm = the protocol validation report (at runtime
# always the canonical PipelexValidationReport subtype), invalid arm = the refusal's
# BundleValidationFailure. Bound at runtime (not just under TYPE_CHECKING) so an external validator
# plugin can import it to annotate its own validate_bundles. Both arms are leaf types w.r.t.
# the hub, so this hub-reachable seam stays import-acyclic even with the runtime imports.
BundleValidationVerdict: TypeAlias = ValidationReport[Any] | BundleValidationFailure


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

    ``submitted_files`` are the files submitted with ``mthds_contents`` that their steps read,
    such as a ``PipeDocGen`` step's ``template_file``, keyed by canonical bundle-relative path,
    with their bytes. The validation loads the bundles with them and its dry run reads them, the
    template check included. It is required for the same reason as ``caller_identity``, with
    ``None`` meaning none were submitted: a validator that dropped them would refuse a valid bundle
    for a missing file. A worker-dispatched arm hands them to its worker through the method file
    store, the crate naming their tree by digest.

    ``method_dir`` names the caller's method as a tree in place of ``mthds_contents``, which is then
    ``None``: the directory of a tree the host wrote out on its own disk, such as a request's map of
    file entries or a fetched package, held as written (``pipelex.libraries.written_trees``). Every
    bundle of the tree is validated, its Python included, and every refusal is the caller's verdict,
    naming the tree's files by their tree paths. ``methods_dirs``, laid out like ``.mthds/methods/``,
    hold the dependency trees the caller ships with it. Both are required for the same reason as
    ``caller_identity``, ``None`` meaning the method came as contents. A worker-dispatched arm reads
    the tree's files on the host, where it is called, and hands them to its worker as trees.

    ``read_scope`` is the scope the host named for the validation: on a multi-tenant host, the
    organization it serves, the trusted prefix a run of the same request reads under
    (``pipelex.tools.uri.uri_read_scope``). It is the scope of the blob store a worker-dispatched arm
    hands the method to its worker through, as a run's orchestrator and worker do under the run's read
    scope: the arm holds every tree it validates in that store, a tree the host already recorded there
    included, names each by its digest, and the worker reads them through its method file store under
    the scope, building every key from it and never from what the request names. ``None`` means the
    host named no scope, as a single-tenant deployment does, or a multi-tenant host serving a caller
    who belongs to no organization: no blob store is then scoped to the caller, so a worker-dispatched
    arm has none to hand the method through and must not make one up, such as one under the caller's
    id, where nothing lists or erases what a validation would leave.
    The in-process arm reads every file in its own process and ignores it. It is required for the
    same reason as ``caller_identity``: a validator that dropped it would read the method under no
    scope.
    """

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str] | None,
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: "Sequence[Path] | None",
        caller_identity: CallerIdentity | None,
        graph_pipe_code: str | None,
        submitted_files: "Mapping[str, bytes] | None",
        method_dir: "Path | None",
        methods_dirs: "Sequence[Path] | None",
        read_scope: str | None,
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
