"""Primary-blueprint selection for a validated batch.

One selection rule shared by every surface that needs a batch's main pipe (the canonical
report's ``bundle_blueprint``, the graph arm's target derivation, the Temporal activity,
library acquisition, dry-run and inputs derivation) — one rule, one implementation.

Lives in its own dedicated module (not next to ``validate_bundle``) so that callers below
the validation layer (``execution_seams``, ``dry_run_pipeline``, ``inputs_ops``) can use it
without an import cycle through ``bundle_validator``.
"""

from typing import NamedTuple, Sequence

from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipeline.exceptions import ValidateBundleError


class PrimaryBlueprintSelection(NamedTuple):
    """The primary blueprint of a validated batch and its domain-qualified main-pipe ref (if any)."""

    blueprint: PipelexBundleBlueprint
    main_pipe_ref: str | None


def select_primary_blueprint(blueprints: Sequence[PipelexBundleBlueprint]) -> PrimaryBlueprintSelection:
    """Select the primary blueprint of a batch: first declaring ``main_pipe``, else first.

    The single selection rule shared by every surface that needs a batch's main pipe (the
    canonical report's ``bundle_blueprint``, the graph arm's target derivation, the Temporal
    activity, library acquisition, dry-run and inputs derivation) — one rule, one
    implementation. ``main_pipe_ref`` is the domain-qualified ref of the primary blueprint's
    ``main_pipe``, or ``None`` when no blueprint in the batch declares one.

    Args:
        blueprints: The batch's blueprints, in declaration order.

    Returns:
        The primary blueprint and its qualified main-pipe ref.

    Raises:
        ValidateBundleError: When ``blueprints`` is empty — a caller error (e.g. an empty
            ``mthds_contents`` array reaching a hosted runner), surfaced as the structured
            input-error class every validate surface already maps, never a bare IndexError.
    """
    if not blueprints:
        msg = "Cannot select a primary blueprint from an empty batch: no MTHDS contents were provided."
        raise ValidateBundleError(message=msg)
    for blueprint in blueprints:
        if blueprint.main_pipe:
            main_pipe_ref = PipeFactory.make_pipe_ref_with_domain(domain_code=blueprint.domain, pipe_code=blueprint.main_pipe)
            return PrimaryBlueprintSelection(blueprint=blueprint, main_pipe_ref=main_pipe_ref)
    return PrimaryBlueprintSelection(blueprint=blueprints[0], main_pipe_ref=None)


def collect_entry_pipe_refs(blueprints: Sequence[PipelexBundleBlueprint]) -> list[str]:
    """The domain-qualified ``main_pipe`` of every blueprint in a batch, in declaration order.

    An *entry pipe* is where a method meets its caller — a human, a form, an API client — which is
    the boundary the advisory entry-pipe lints are scoped to. A blueprint that declares no
    ``main_pipe`` contributes nothing, so a batch with none yields an empty list rather than
    guessing at one.

    Distinct from :func:`select_primary_blueprint`, which picks the ONE main pipe a batch is
    canonically about (its graph target, its dry-run target). Both qualify a ``main_pipe`` the same
    way, but a lint that must judge every declared entry point cannot use a rule that returns one.

    Args:
        blueprints: The batch's blueprints, in declaration order.

    Returns:
        The qualified entry-pipe refs, in the same order.
    """
    return [
        PipeFactory.make_pipe_ref_with_domain(domain_code=blueprint.domain, pipe_code=blueprint.main_pipe)
        for blueprint in blueprints
        if blueprint.main_pipe
    ]
