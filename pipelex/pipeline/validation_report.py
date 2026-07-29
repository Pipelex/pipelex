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
from typing import Literal

from mthds.protocol.models import ValidationReport
from pydantic import Field

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.graph.graphspec import GraphSpec
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipeline.blueprint_selection import select_primary_blueprint
from pipelex.pipeline.bundle_validator import DryRunOutput
from pipelex.pipeline.liftable_pipes import LiftablePipeEntry
from pipelex.pipeline.pipe_io_contracts import PipeIOContract
from pipelex.pipeline.validate_bundle import ValidatedPipeEntry, build_validated_pipes
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class PipelexValidationReport(ValidationReport):
    """Pipelex's validation artifacts — this implementation's extensions on the
    protocol's `ValidationReport` (which declares no body fields).

    Field naming follows the brand boundary: blueprints are MTHDS-language artifacts
    (the parsed form of `.mthds` content), so the field is `bundle_blueprint` — no
    `pipelex_` prefix inside this already-Pipelex-branded envelope.
    """

    is_valid: Literal[True] = True
    """Always `True` on this report — the discriminant of the valid arm of the HTTP response
    union (mirrored by pipelex-api's `InvalidReport` `Literal[False]`). Self-describing, sits
    beside `is_runnable`: a sound bundle may still be not-yet-runnable (pending signatures)."""

    bundle_blueprint: PipelexBundleBlueprint
    """The batch's primary blueprint: first declaring `main_pipe`, else first."""

    pipe_io_contracts: dict[str, PipeIOContract] = Field(default_factory=dict)
    """Per-pipe input/output contracts, keyed by namespaced `pipe_ref` (`domain.code`)."""

    liftable_pipes: list[LiftablePipeEntry] = Field(default_factory=empty_list_factory_of(LiftablePipeEntry))
    """Pipes that may be skipped (lifted) when an optional slot resolves absent — the
    build-time visibility that the implicit-lifting design (D3) commits to."""

    graph_spec: GraphSpec | None = None
    """Best-effort execution graph of the declared main pipe; `None` when the batch
    declares no `main_pipe` or the graph dry-run degrades."""

    validated_pipes: list[ValidatedPipeEntry] = Field(default_factory=empty_list_factory_of(ValidatedPipeEntry))
    """Per-pipe sweep outcomes (`{pipe_ref, status}`) — the same entries as the agent-CLI envelope."""

    warnings: list[ValidationErrorItem] = Field(default_factory=empty_list_factory_of(ValidationErrorItem))
    """Advisory findings (lints) on a VALID bundle — same item shape as `validation_errors`,
    but they never flip `is_valid`. First occupant: the useless-`!` lint
    (`optional_force_redundant`)."""

    pending_signatures: list[str] = Field(default_factory=list)
    """Qualified refs of pipes still declared as `PipeSignature` in the assembled library."""

    is_runnable: bool = True
    """`not pending_signatures` — whether the validated library is complete enough to run."""


def build_validation_report(
    *,
    blueprints: Sequence[PipelexBundleBlueprint],
    pipe_io_contracts: dict[str, PipeIOContract],
    dry_run_result: dict[str, DryRunOutput],
    pending_signatures: list[str],
    graph_spec: GraphSpec | None = None,
    liftable_pipes: list[LiftablePipeEntry] | None = None,
    warnings: list[ValidationErrorItem] | None = None,
) -> PipelexValidationReport:
    """Assemble the canonical `PipelexValidationReport` from its ingredients.

    The single constructor every backend calls — local protocol `validate` and the hosted
    API's Temporal mapping. Selects the primary blueprint, projects the dry-run status map
    into `validated_pipes`, and derives the `is_runnable` verdict.

    Args:
        blueprints: The validated batch's blueprints, in declaration order (non-empty).
        pipe_io_contracts: Per-pipe contracts from `build_pipe_io_contracts`, keyed by `pipe_ref`.
        dry_run_result: The sweep's per-pipe status map (`ValidateBundleResult.dry_run_result`).
        pending_signatures: Library-wide unsatisfied signature refs.
        graph_spec: Best-effort graph of the declared main pipe, when one was produced.
        liftable_pipes: Entries from `build_liftable_pipes`, when the caller computed them.
        warnings: Advisory items from `build_optionality_warnings`, when the caller computed them.

    Returns:
        The canonical report.
    """
    return PipelexValidationReport(
        bundle_blueprint=select_primary_blueprint(blueprints).blueprint,
        pipe_io_contracts=pipe_io_contracts,
        liftable_pipes=liftable_pipes or [],
        graph_spec=graph_spec,
        validated_pipes=build_validated_pipes(dry_run_result),
        pending_signatures=pending_signatures,
        is_runnable=not pending_signatures,
        warnings=warnings or [],
    )
