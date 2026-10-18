"""The core, always-on in-process bundle validator.

Validates MTHDS bundles in-process via ``validate_bundles_in_process``, the same sweep
the local protocol runtime uses. Returns the verdict as a value (decision A): the canonical
``PipelexValidationReport`` on success, or the ``BundleValidationFailure`` of an invalid bundle's
``ValidateBundleError``. Any other exception propagates as a no-verdict fault.

Registered unconditionally by the core ``direct`` plugin alongside ``DirectOrchestrator``, so
the agnostic base gets in-process ``/validate`` "for free" through the same seam the Temporal
plugin contributes to. Import-light: core validation machinery only, no host-runtime SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_in_process import validate_bundles_in_process

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from pipelex.pipeline.validation_report import PipelexValidationReport
    from pipelex.system.caller_identity import CallerIdentity


class DirectBundleValidator:
    """In-process ``/validate``; loads and tears down the method library on the host.

    Satisfies ``BundleValidatorProtocol`` structurally. Returns the precise
    ``PipelexValidationReport`` on the valid arm (a covariant narrowing of the protocol's
    ``ValidationReport`` valid arm) so a caller holding the concrete class keeps full type
    information; the protocol stays widened to the leaf base to keep core import-acyclic.
    """

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str] | None,
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: Sequence[Path] | None,
        caller_identity: CallerIdentity | None,
        graph_pipe_code: str | None,
        submitted_files: Mapping[str, bytes] | None,
        method_dir: Path | None,
        methods_dirs: Sequence[Path] | None,
        # The in-process arm reads every file of the method in this process, from the trees its libraries hold, and
        # reads no blob store, so the scope a dispatched arm hands its worker the trees through has no use here.
        read_scope: str | None,  # ruff: ignore[unused-method-argument]
    ) -> PipelexValidationReport | BundleValidationFailure:
        try:
            return await validate_bundles_in_process(
                mthds_contents=mthds_contents,
                mthds_sources=mthds_sources,
                library_dirs=library_dirs,
                allow_signatures=allow_signatures,
                graph_pipe_code=graph_pipe_code,
                log_context="API validate",
                caller_identity=caller_identity,
                submitted_files=submitted_files,
                method_dir=method_dir,
                methods_dirs=methods_dirs,
            )
        except ValidateBundleError as exc:
            # An invalid bundle is a produced verdict, not a fault: surface its problem and its items
            # as the invalid arm. Any other exception (a fault with no verdict) propagates.
            return BundleValidationFailure(problem=exc.to_problem(view=ProblemView.OPERATOR), validation_errors=exc.validation_error_items())
