"""The one sequence that derives a method's three I/O artifacts, off one crate qualification.

`validate_bundles_in_process` used to spell it out inline — contracts, one
`qualify_current_library_crate()`, both forms off the same qualification — and a run now needs the
same sequence at the end of `PipeRun.run`. Keeping it in one place means a validate report and a
run's results directory cannot drift on how the artifacts are derived, and a future fourth
artifact is populated everywhere or nowhere.

The three builders need the live library: JSON-Schema rendering resolves bundle-defined structure
classes through the class registry, and the forms qualify the current library's crate. So this
must run inside a library window — the validate orchestrator's, or the run's own before
`PipelineRunner.execute` tears the run library down. The carrier it returns, `PipeIOArtifacts`,
lives apart because `PipeOutput` imports it and must stay free of the library machinery.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.core.pipes.pipe_io_artifacts import PipeIOArtifacts
from pipelex.pipeline.input_form import build_input_form, build_output_form, qualify_current_library_crate
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.libraries.crate_qualification import QualifiedCrateContent
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


def build_pipe_io_artifacts(pipes: Sequence[PipeAbstract], *, qualified_crate: QualifiedCrateContent | None = None) -> PipeIOArtifacts:
    """Build the three artifacts over the given pipes, off one crate qualification.

    Must run inside a library window (see the module docstring).

    Args:
        pipes: The loaded pipes to describe: a validated bundle's, or a run library's.
        qualified_crate: The current library's already-qualified crate, when the caller holds one;
            otherwise the crate is read and qualified here, once for both forms.

    Returns:
        The three artifacts, sharing one key set.

    Raises:
        PipeIOContractError: When a pipe's output JSON Schema cannot be rendered.
    """
    pipe_io_contracts = build_pipe_io_contracts(pipes)
    qualified = qualified_crate if qualified_crate is not None else qualify_current_library_crate()
    return PipeIOArtifacts(
        pipe_io_contracts=pipe_io_contracts,
        input_form=build_input_form(pipes, qualified_crate=qualified),
        output_form=build_output_form(pipes, qualified_crate=qualified),
    )
