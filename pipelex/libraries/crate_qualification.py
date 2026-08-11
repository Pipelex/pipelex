"""Qualification pass: in-body references -> fully-qualified refs, over a library crate.

Given a merged, key-qualified crate (keys are `domain.Code` / `domain.code`, as produced by
`LibraryCrateFactory.make_from_blueprints`), this pass rewrites every *in-body* reference into the
form the rest of the system can resolve by key:

- concept `refines` and structure-field `concept_ref` / `item_concept_ref`;
- pipe `inputs` / `output` concept refs, preserving multiplicity and presence markers;
- pipe-step / branch / outcome / batch pipe refs.

**A bare ref names its own domain.** Both halves follow the same rule — a bare pipe code resolves to
the domain of the pipe that wrote it, exactly as a bare concept code does. Nothing is searched for
across the crate. An in-body reference that can silently land in a domain the author never named is
a reference no `[exports]` rule can constrain, and a visibility rule the resolver reaches around is
not a visibility rule.

**Existence is deliberately not checked here.** The pass runs once per load batch, and a batch may
legitimately reference a pipe that a *prior* batch loaded into the same domain — a `-L` library
directory, a secondary load. Only ordinary dependency validation sees the whole live library, so
that is where a genuinely missing ref is reported, with the qualified ref it tried.

Two kinds of ref are deliberately left alone: cross-package (`alias->…`) refs, whose canonical form
is the packaging project's design work, and `SpecialOutcome` values (`fail` / `continue`), which are
condition outcomes rather than pipe refs.

The pass is idempotent: an already-qualified ref is returned unchanged, so running it twice over the
same crate is the same as running it once. It does not mutate the crate it is given.

**It returns only what it computed** — the rewritten `concepts` and `pipes`, not a `LibraryCrate`.
Handing back a crate would force the pass to supply a `fingerprint` it has no way to get right: a
crate does not record which digest scheme produced its value (`compute_fingerprint_from_content` for
a merged crate, `compute_normalized_fingerprint` for a normalized one), so the pass would either
guess or carry over a digest that no longer describes its own content. Returning the two mappings
makes that contradiction unrepresentable and costs the callers nothing — both of them already own a
crate to read the envelope from, and `normalize_crate` builds a fresh one anyway.
"""

from typing import NamedTuple

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptStructureBlueprintType
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint
from pipelex.core.pipes.variable_multiplicity import MultiplicityParseResult, parse_concept_with_multiplicity
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.exceptions import CrateNormalizationError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint

_ConceptEntry = ConceptBlueprint | str


class QualifiedCrateContent(NamedTuple):
    """A crate's `concepts` and `pipes` with every in-body reference qualified."""

    concepts: dict[str, _ConceptEntry]
    pipes: dict[str, PipeBlueprintUnion]


def qualify_crate(crate: LibraryCrate) -> QualifiedCrateContent:
    """Qualify every in-body reference of a merged, key-qualified crate.

    Raises:
        CrateNormalizationError: A crate key is not domain-qualified — the pass was handed something
            that is not a merged, key-qualified crate.
    """
    concepts: dict[str, _ConceptEntry] = {
        concept_ref: _qualify_concept_entry(value, owner_domain=_domain_of(concept_ref)) for concept_ref, value in crate.concepts.items()
    }

    pipes: dict[str, PipeBlueprintUnion] = {
        pipe_ref: _qualify_pipe_blueprint(blueprint, owner_domain=_domain_of(pipe_ref)) for pipe_ref, blueprint in crate.pipes.items()
    }

    return QualifiedCrateContent(concepts=concepts, pipes=pipes)


def _domain_of(qualified_ref: str) -> str:
    domain_path = QualifiedRef.parse(qualified_ref).domain_path
    if domain_path is None:
        # "the normalizer" would be wrong now: the library build calls this pass too, and is the
        # busier caller of the two.
        msg = f"Crate key '{qualified_ref}' is not domain-qualified; this pass expects a merged, key-qualified crate."
        raise CrateNormalizationError(msg)
    return domain_path


# --------------------------------------------------------------------------------------------------
# Concepts
# --------------------------------------------------------------------------------------------------


def _qualify_concept_entry(value: _ConceptEntry, *, owner_domain: str) -> _ConceptEntry:
    # A string-described concept is a description, so it holds no references to qualify.
    if isinstance(value, str):
        return value

    updates: dict[str, object] = {}
    if value.refines:
        updates["refines"] = ConceptFactory.make_refine(value.refines, domain_code=owner_domain)
    if isinstance(value.structure, dict):
        qualified_structure: dict[str, ConceptStructureBlueprintType] = {}
        for field_name, field in value.structure.items():
            # A string field is a shorthand description, materialized into an explicit text field by
            # the normalizer; it carries no concept ref either way.
            if isinstance(field, ConceptStructureBlueprint):
                qualified_structure[field_name] = _qualify_structure_field(field, domain=owner_domain)
            else:
                qualified_structure[field_name] = field
        updates["structure"] = qualified_structure
    return value.model_copy(update=updates) if updates else value


def _qualify_structure_field(field_blueprint: ConceptStructureBlueprint, *, domain: str) -> ConceptStructureBlueprint:
    field_updates: dict[str, object] = {}
    if field_blueprint.concept_ref:
        field_updates["concept_ref"] = _qualify_concept_ref(field_blueprint.concept_ref, domain=domain)
    if field_blueprint.item_concept_ref:
        field_updates["item_concept_ref"] = _qualify_concept_ref(field_blueprint.item_concept_ref, domain=domain)
    return field_blueprint.model_copy(update=field_updates) if field_updates else field_blueprint


def _qualify_concept_ref(concept_ref_or_code: str, *, domain: str) -> str:
    # make_concept_ref_with_domain_from_concept_ref_or_code resolves natives to `native.<Code>`,
    # bare refs to `domain.<Code>`, and preserves cross-package `alias->domain.Code` as-is (deferred).
    return ConceptFactory.make_concept_ref_with_domain_from_concept_ref_or_code(domain_code=domain, concept_ref_or_code=concept_ref_or_code)


# --------------------------------------------------------------------------------------------------
# Pipes
# --------------------------------------------------------------------------------------------------


def _qualify_pipe_blueprint(blueprint: PipeBlueprintUnion, *, owner_domain: str) -> PipeBlueprintUnion:
    updates: dict[str, object] = {}
    if blueprint.inputs:
        updates["inputs"] = {name: _qualify_io_ref(ref, domain=owner_domain) for name, ref in blueprint.inputs.items()}
    if blueprint.output:
        updates["output"] = _qualify_io_ref(blueprint.output, domain=owner_domain)

    def qualify(*, pipe_ref: str) -> str:
        return _qualify_pipe_ref(pipe_ref, owner_domain=owner_domain)

    def qualify_outcome(*, outcome: str) -> str:
        """A condition outcome may be a `SpecialOutcome` instead of a pipe ref.

        The exemption belongs *here* and nowhere else. `fail` and `continue` are legal snake_case pipe
        codes, so a sequence step, a parallel branch or a batch target may genuinely name a pipe
        called `continue` — exempting those too would leave a real ref unqualified, and under the
        strict lookup it would then resolve to nothing.
        """
        if outcome in SpecialOutcome.value_list():
            return outcome
        return _qualify_pipe_ref(outcome, owner_domain=owner_domain)

    match blueprint:
        case PipeSequenceBlueprint():
            updates["steps"] = [step.model_copy(update={"pipe": qualify(pipe_ref=step.pipe)}) for step in blueprint.steps]
        case PipeParallelBlueprint():
            updates["branches"] = [branch.model_copy(update={"pipe": qualify(pipe_ref=branch.pipe)}) for branch in blueprint.branches]
        case PipeConditionBlueprint():
            if blueprint.outcomes:
                updates["outcomes"] = {key: qualify_outcome(outcome=outcome) for key, outcome in blueprint.outcomes.items()}
            if blueprint.default_outcome:
                updates["default_outcome"] = qualify_outcome(outcome=blueprint.default_outcome)
        case PipeBatchBlueprint():
            if blueprint.branch_pipe_code:
                updates["branch_pipe_code"] = qualify(pipe_ref=blueprint.branch_pipe_code)
        case _:
            # Every controller kind that embeds a pipe ref is named above; operators embed none, so
            # they fall through with only their inputs/output rewritten. A NEW controller kind lands
            # here silently — `test_normalized_crate_is_closed_over_its_pipe_refs` is what catches it,
            # by walking `pipe_dependencies` rather than the kinds this match enumerates.
            pass

    return blueprint.model_copy(update=updates)


def _qualify_io_ref(io_ref: str, *, domain: str) -> str:
    if QualifiedRef.has_cross_package_prefix(io_ref):
        return io_ref  # cross-package deferred
    parsed = parse_concept_with_multiplicity(io_ref)
    qualified = _qualify_concept_ref(parsed.concept_ref_or_code, domain=domain)
    return _render_ref_with_markers(qualified, parsed=parsed)


def _render_ref_with_markers(concept_ref: str, *, parsed: MultiplicityParseResult) -> str:
    if parsed.multiplicity is True:
        suffix = "[]"
    elif isinstance(parsed.multiplicity, int):
        suffix = f"[{parsed.multiplicity}]"
    else:
        suffix = ""
    return f"{concept_ref}{suffix}{parsed.presence.symbol}"


def _qualify_pipe_ref(pipe_ref: str, *, owner_domain: str) -> str:
    """Qualify one in-body pipe ref to the domain of the pipe that wrote it.

    The exact twin of `_qualify_concept_ref`, and unconditional: a bare code is the owner domain's,
    whether or not the owner domain declares it. Nothing is searched for, so nothing can be found
    somewhere the author did not name — which is what makes `[exports]` mean something.

    A ref that names nothing is not this function's problem. It cannot be: the pass sees one load
    batch, and a batch may reference a pipe a prior batch put in the same domain. Dependency
    validation sees the whole live library and reports the miss there, naming the qualified ref.
    """
    if QualifiedRef.has_cross_package_prefix(pipe_ref):
        return pipe_ref  # cross-package deferred
    if "." in pipe_ref:
        return pipe_ref
    return f"{owner_domain}.{pipe_ref}"
