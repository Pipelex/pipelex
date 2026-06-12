"""Per-pipe input/output contracts (`pipe_structures`) for the validate surfaces.

This is the canonical builder for the `pipe_structures` artifact reported by the MTHDS
Protocol `validate` operation (local runtime and hosted API alike). It projects loaded
pipes into typed `PipeIOContract` entries — for each pipe, the JSON-Schema view of its
declared inputs and the concept/multiplicity of its output — keyed by the namespaced
`pipe_ref` (`domain.code`), the one identity convention shared by every validate artifact
(`validated_pipes`, `pending_signatures`).

The JSON-Schema rendering resolves each concept's structure class through the GLOBAL
class registry. Bundle-defined structure classes are registered there during library
load and are NOT unregistered at teardown (the registry has no unregister mechanism) —
so a call after teardown does not fail loudly: it silently renders against whatever
classes the registry last held, which may be stale or belong to a different bundle.
Callers must therefore invoke the builder against loaded pipes INSIDE the validation
library's window, before teardown. (Registry teardown hygiene is tracked in the
workspace-root `wip/library-lifecycle-hygiene.md`.)
"""

from typing import Any, NamedTuple, Sequence

from pydantic import BaseModel, Field, PydanticUndefinedAnnotation, PydanticUserError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipeline.exceptions import PipeStructuresError, ValidateBundleError
from pipelex.types import StrEnum


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

    Lives in this low-level module (not next to ``validate_bundle``) so that callers below
    the validation layer (``execution_seams``, ``dry_run_pipeline``) can use it without an
    import cycle through ``bundle_validator``.

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


class IOMultiplicity(StrEnum):
    """Wire value for an output's multiplicity: one item, or a list of them.

    Any multiple output — variable-length or fixed-count — reports `variable`; the
    distinction the contract carries is "one vs many", not the exact count.
    """

    SINGLE = "single"
    VARIABLE = "variable"


class PipeInputContract(BaseModel):
    """One declared input: the concept it expects and the JSON Schema of its content."""

    concept_code: str
    json_schema: dict[str, Any] = Field(default_factory=dict)


class PipeOutputContract(BaseModel):
    """The pipe's output: the concept it produces and whether it is one item or a list."""

    concept_code: str
    multiplicity: IOMultiplicity


class PipeIOContract(BaseModel):
    """The input/output contract of one pipe — a `pipe_structures` entry."""

    inputs: dict[str, PipeInputContract] = Field(default_factory=dict)
    output: PipeOutputContract


def build_pipe_structures(pipes: Sequence[PipeAbstract]) -> dict[str, PipeIOContract]:
    """Project loaded pipes into `pipe_structures` entries keyed by namespaced `pipe_ref`.

    Works on any loaded `PipeAbstract` — including `PipeSignature` placeholders, whose
    declared contract is exactly what a top-down build needs to see. Must run while the
    validation library is still loaded: bundle-defined structure classes resolve through
    the global class registry and a post-teardown call silently uses stale classes
    instead of failing (see the module docstring).

    Args:
        pipes: The loaded pipes to project (typically `ValidateBundleResult.pipes`).

    Returns:
        `pipe_ref` → `PipeIOContract` for every given pipe.

    Raises:
        PipeStructuresError: When a pipe input's JSON-Schema rendering fails (a pydantic
            schema-generation error on a structure class) — converted here so every
            validate surface reports the same structured error.
    """
    # Per-call memo: pipes routinely share input concepts, and the JSON-Schema rendering
    # (pydantic's model_json_schema, uncached) would otherwise be regenerated once per
    # occurrence. Deliberately NOT a module-level cache — bundle-defined structure classes
    # vary per loaded library, so a cross-call cache would serve stale schemas.
    schema_memo: dict[tuple[str, bool], dict[str, Any]] = {}
    structures: dict[str, PipeIOContract] = {}
    for pipe in pipes:
        pipe_inputs: dict[str, PipeInputContract] = {}
        for var_name, stuff_spec in pipe.inputs.root.items():
            memo_key = (stuff_spec.concept.concept_ref, stuff_spec.is_multiple())
            schema_repr = schema_memo.get(memo_key)
            if schema_repr is None:
                try:
                    schema_repr = stuff_spec.render_stuff_spec(ConceptRepresentationFormat.SCHEMA)
                except (PydanticUserError, PydanticUndefinedAnnotation) as exc:
                    msg = (
                        f"Failed to render the JSON Schema for input '{var_name}' of pipe "
                        f"'{pipe.pipe_ref}' (concept '{stuff_spec.concept.concept_ref}'): {exc}"
                    )
                    raise PipeStructuresError(message=msg) from exc
                schema_memo[memo_key] = schema_repr
            pipe_inputs[var_name] = PipeInputContract(
                concept_code=schema_repr.get("concept", ""),
                json_schema=schema_repr.get("content", {}),
            )
        pipe_output = PipeOutputContract(
            concept_code=pipe.output.concept.concept_ref,
            multiplicity=IOMultiplicity.VARIABLE if pipe.output.is_multiple() else IOMultiplicity.SINGLE,
        )
        structures[pipe.pipe_ref] = PipeIOContract(inputs=pipe_inputs, output=pipe_output)
    return structures
