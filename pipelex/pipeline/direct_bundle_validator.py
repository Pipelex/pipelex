"""The core, always-on in-process bundle validator.

Validates MTHDS bundles in-process via ``validate_bundles_in_process``, the same sweep
the local protocol runtime uses. Returns the verdict as a value (decision A): the canonical
``PipelexValidationReport`` on success, or the structured ``ErrorReport`` an invalid bundle's
``ValidateBundleError`` projects. Any other exception propagates as a no-verdict infra fault.

Registered unconditionally by the core ``direct`` plugin alongside ``DirectOrchestrator``, so
the agnostic base gets in-process ``/validate`` "for free" through the same seam the Temporal
plugin contributes to. Import-light: core validation machinery only, no host-runtime SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_in_process import validate_bundles_in_process

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from pipelex.base_exceptions import ErrorReport
    from pipelex.pipeline.validation_report import PipelexValidationReport


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
        mthds_contents: list[str],
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: Sequence[Path] | None,
    ) -> PipelexValidationReport | ErrorReport:
        try:
            return await validate_bundles_in_process(
                mthds_contents=mthds_contents,
                mthds_sources=mthds_sources,
                library_dirs=library_dirs,
                allow_signatures=allow_signatures,
                log_context="API validate",
            )
        except ValidateBundleError as exc:
            # An invalid bundle is a produced verdict, not a fault: surface its structured
            # report as the invalid arm. Any other exception (genuine infra fault) propagates.
            return exc.to_error_report()
