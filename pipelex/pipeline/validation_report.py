"""Canonical MTHDS Protocol validation report for the Pipelex family.

`PipelexValidationReport` is the one report shape every Pipelex backend produces for the
protocol `validate` operation — the local runtime (`PipelexMTHDSProtocol.validate`) and the
hosted API (`ApiRunner.validate`, direct and Temporal alike). All fields are typed models,
not raw dumps, so the schemas flow into the hosted API's committed OpenAPI artifact.

`build_validation_report` is the single assembly point: both backends construct the report
through it from the same ingredients, so a future report field is populated everywhere or
nowhere. Primary-blueprint selection (`bundle_blueprint`) goes through
`select_primary_blueprint` — the same rule the graph arm uses for its target.
"""

from collections.abc import Sequence

from mthds.protocol.models import ValidationReport
from pydantic import Field

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.graph.graphspec import GraphSpec
from pipelex.pipeline.bundle_validator import DryRunOutput
from pipelex.pipeline.pipe_structures import PipeIOContract
from pipelex.pipeline.validate_bundle import ValidatedPipeEntry, build_validated_pipes, select_primary_blueprint
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class PipelexValidationReport(ValidationReport):
    """Pipelex's validation artifacts — this implementation's extensions on the
    protocol's `ValidationReport` (which declares no body fields).

    Field naming follows the brand boundary: blueprints are MTHDS-language artifacts
    (the parsed form of `.mthds` content), so the field is `bundle_blueprint` — no
    `pipelex_` prefix inside this already-Pipelex-branded envelope.
    """

    bundle_blueprint: PipelexBundleBlueprint
    """The batch's primary blueprint: first declaring `main_pipe`, else first."""

    pipe_structures: dict[str, PipeIOContract] = Field(default_factory=dict)
    """Per-pipe input/output contracts, keyed by namespaced `pipe_ref` (`domain.code`)."""

    graph_spec: GraphSpec | None = None
    """Best-effort execution graph of the declared main pipe; `None` when the batch
    declares no `main_pipe` or the graph dry-run degrades."""

    validated_pipes: list[ValidatedPipeEntry] = Field(default_factory=empty_list_factory_of(ValidatedPipeEntry))
    """Per-pipe sweep outcomes (`{pipe_ref, status}`) — the same entries as the agent-CLI envelope."""

    pending_signatures: list[str] = Field(default_factory=list)
    """Qualified refs of pipes still declared as `PipeSignature` in the assembled library."""

    is_runnable: bool = True
    """`not pending_signatures` — whether the validated library is complete enough to run."""


def build_validation_report(
    *,
    blueprints: Sequence[PipelexBundleBlueprint],
    pipe_structures: dict[str, PipeIOContract],
    dry_run_result: dict[str, DryRunOutput],
    pending_signatures: list[str],
    graph_spec: GraphSpec | None = None,
) -> PipelexValidationReport:
    """Assemble the canonical `PipelexValidationReport` from its ingredients.

    The single constructor every backend calls — local protocol `validate` and the hosted
    API's Temporal mapping. Selects the primary blueprint, projects the dry-run status map
    into `validated_pipes`, and derives the `is_runnable` verdict.

    Args:
        blueprints: The validated batch's blueprints, in declaration order (non-empty).
        pipe_structures: Per-pipe contracts from `build_pipe_structures`, keyed by `pipe_ref`.
        dry_run_result: The sweep's per-pipe status map (`ValidateBundleResult.dry_run_result`).
        pending_signatures: Library-wide unsatisfied signature refs.
        graph_spec: Best-effort graph of the declared main pipe, when one was produced.

    Returns:
        The canonical report.
    """
    return PipelexValidationReport(
        bundle_blueprint=select_primary_blueprint(blueprints).blueprint,
        pipe_structures=pipe_structures,
        graph_spec=graph_spec,
        validated_pipes=build_validated_pipes(dry_run_result),
        pending_signatures=pending_signatures,
        is_runnable=not pending_signatures,
    )
