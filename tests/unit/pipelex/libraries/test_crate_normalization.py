from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.exceptions import CrateNormalizationError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

MTHDS_TEST_VERSION = "0.1.0-test"


def _structure_field(concept: ConceptBlueprint | str, field_name: str) -> ConceptStructureBlueprint:
    """Narrow a concept's structure field to a `ConceptStructureBlueprint` for typed assertions."""
    assert isinstance(concept, ConceptBlueprint)
    assert isinstance(concept.structure, dict)
    field = concept.structure[field_name]
    assert isinstance(field, ConceptStructureBlueprint)
    return field


def _authored_crate() -> LibraryCrate:
    """A merged, key-qualified single-package crate exercising every normalization step.

    All keys are domain-qualified (`scoring.*`) as `LibraryCrateFactory` would leave them; in-body
    references are authored bare (same-domain codes and native codes) so the normalizer has work to do.
    """
    return LibraryCrate(
        concepts={
            # String-described concept -> promoted to a description-only ConceptBlueprint.
            "scoring.Category": "A category label",
            # Structure with a bare same-domain concept_ref and a bare native concept_ref.
            "scoring.WeightedScore": ConceptBlueprint(
                description="A weighted score",
                structure={
                    "value": ConceptStructureBlueprint(description="the numeric value", type=ConceptStructureBlueprintFieldType.NUMBER),
                    "label": ConceptStructureBlueprint(
                        description="the category", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Category"
                    ),
                    "note": ConceptStructureBlueprint(
                        description="a free-text note", type=ConceptStructureBlueprintFieldType.CONCEPT, concept_ref="Text"
                    ),
                },
            ),
            # Refines a same-package concept that HAS a structure -> flattened (refines dropped).
            "scoring.DetailedScore": ConceptBlueprint(description="a detailed score", refines="WeightedScore"),
            # Refines a STRUCTURELESS native (Date, whose content class has no mappable structure) ->
            # refines kept, no structure materialized.
            "scoring.CustomDate": ConceptBlueprint(description="a domain-specific date", refines="Date"),
            # Refines a STRUCTURED native (Text, whose materialized structure has a `text` field) ->
            # refines kept (B1-2): flattening would drop the native base on round-trip.
            "scoring.Summary": ConceptBlueprint(description="a short summary", refines="Text"),
            # Multi-hop: refines a concept that itself bottoms out at a native -> refines kept.
            "scoring.LongSummary": ConceptBlueprint(description="a longer summary", refines="Summary"),
        },
        pipes={
            "scoring.compute_score": PipeLLMBlueprint(
                description="Compute a weighted score",
                inputs={"data": "Text"},
                output="WeightedScore",
                prompt="Compute from $data",
            ),
            "scoring.list_scores": PipeLLMBlueprint(
                description="Compute several weighted scores",
                inputs={"docs": "Text[]"},
                output="WeightedScore[]",
                prompt="List from $docs",
            ),
            "scoring.pipeline": PipeSequenceBlueprint(
                description="Run the scoring pipeline",
                output="WeightedScore",
                steps=[SubPipeBlueprint(pipe="compute_score")],
            ),
        },
        domains={"scoring": DomainBlueprint(code="scoring", description="Scoring domain")},
        source_map={"scoring.WeightedScore": "/fake/scoring.mthds"},
    )


def _cross_domain_crate() -> LibraryCrate:
    """A two-domain crate whose every controller kind calls a *sibling* domain's pipe by bare code.

    The authored shape of `pipelex-cookbook/examples/wip/advisory_board/`: an orchestrator domain
    driving pipes declared in a presentation domain. The library loads and runs, because
    `PipeLibrary.get_optional_pipe` resolves a bare code across every domain.
    """
    return LibraryCrate(
        pipes={
            "orchestrator.run_all": PipeSequenceBlueprint(
                description="Run the advisory board",
                output="Text",
                steps=[SubPipeBlueprint(pipe="present_as_markdown")],
            ),
            "orchestrator.fan_out": PipeParallelBlueprint(
                description="Render both presentations at once",
                inputs={"data": "Text"},
                output="Composite",
                branches=[
                    SubPipeBlueprint(pipe="present_as_markdown", result="markdown"),
                    SubPipeBlueprint(pipe="render_html", result="html"),
                ],
            ),
            "orchestrator.route": PipeConditionBlueprint(
                description="Pick a presentation",
                inputs={"data": "Text"},
                output="Text",
                expression="format",
                outcomes={"markdown": "present_as_markdown"},
                default_outcome="render_html",
            ),
            "orchestrator.route_to_special": PipeConditionBlueprint(
                description="Route to the special outcomes",
                inputs={"data": "Text"},
                output="Text",
                expression="format",
                outcomes={"stop": SpecialOutcome.FAIL},
                default_outcome=SpecialOutcome.CONTINUE,
            ),
            "orchestrator.batch_all": PipeBatchBlueprint(
                description="Present every document",
                inputs={"docs": "Text[]"},
                output="Text[]",
                branch_pipe_code="present_as_markdown",
                input_list_name="docs",
                input_item_name="doc",
            ),
            "presentation.present_as_markdown": PipeLLMBlueprint(
                description="Present as markdown",
                inputs={"data": "Text"},
                output="Text",
                prompt="Present $data as markdown",
            ),
            "presentation.render_html": PipeLLMBlueprint(
                description="Render as HTML",
                inputs={"data": "Text"},
                output="Text",
                prompt="Render $data as HTML",
            ),
        },
        domains={
            "orchestrator": DomainBlueprint(code="orchestrator", description="Orchestrator domain"),
            "presentation": DomainBlueprint(code="presentation", description="Presentation domain"),
        },
    )


def _reverse_refinement_chain_crate(size: int) -> LibraryCrate:
    concepts: dict[str, ConceptBlueprint | str] = {
        f"scale.Node{index:04d}": ConceptBlueprint(description=f"Node {index}", refines=f"Node{index + 1:04d}") for index in range(size - 1)
    }
    concepts[f"scale.Node{size - 1:04d}"] = ConceptBlueprint(
        description="Structured base",
        structure={
            "value": ConceptStructureBlueprint(description="Value", type=ConceptStructureBlueprintFieldType.TEXT),
        },
    )
    return LibraryCrate(concepts=concepts)


class TestCrateNormalization:
    """Unit tests for `normalize_crate` over a hand-built, key-qualified crate."""

    def test_string_concept_promoted_to_blueprint(self):
        """A string-described concept becomes an explicit description-only ConceptBlueprint."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        category = result.concepts["scoring.Category"]
        assert isinstance(category, ConceptBlueprint)
        assert category.description == "A category label"
        assert category.structure is None

    def test_in_body_concept_refs_fully_qualified(self):
        """Bare same-domain and bare native concept refs in a structure become fully qualified."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        weighted = result.concepts["scoring.WeightedScore"]
        assert _structure_field(weighted, "label").concept_ref == "scoring.Category"
        assert _structure_field(weighted, "note").concept_ref == "native.Text"

    def test_pipe_io_refs_qualified_with_multiplicity_preserved(self):
        """Pipe input/output concept refs qualify; multiplicity markers survive the rewrite."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        compute = result.pipes["scoring.compute_score"]
        assert compute.inputs == {"data": "native.Text"}
        assert compute.output == "scoring.WeightedScore"
        listed = result.pipes["scoring.list_scores"]
        assert listed.inputs == {"docs": "native.Text[]"}
        assert listed.output == "scoring.WeightedScore[]"

    def test_sequence_step_pipe_refs_qualified(self):
        """A sequence step's bare pipe ref is qualified with the domain that declares the callee."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        pipeline = result.pipes["scoring.pipeline"]
        assert isinstance(pipeline, PipeSequenceBlueprint)
        assert pipeline.steps[0].pipe == "scoring.compute_score"

    @pytest.mark.parametrize("crate_factory", [_authored_crate])
    def test_normalized_crate_is_closed_over_its_pipe_refs(self, crate_factory: Callable[[], LibraryCrate]):
        """Every in-body pipe ref of a normalized crate names a pipe the crate actually holds.

        Driven off `pipe_dependencies` rather than a hand-walk of the controller kinds, so a new kind —
        or a new `crate_qualification._qualify_pipe_ref` call site on an existing one — is covered the
        day it lands. An open ref is silent: the crate hashes content nobody can resolve, and a
        round-trip through `load_from_crate` dies with `PipeNotFoundError` at run time instead of at
        normalization.
        """
        result = normalize_crate(crate_factory(), mthds_version=MTHDS_TEST_VERSION)
        dangling = {
            f"{pipe_ref} -> {dependency}"
            for pipe_ref, blueprint in result.pipes.items()
            for dependency in blueprint.pipe_dependencies
            if dependency not in result.pipes
        }
        assert not dangling

    def test_bare_pipe_refs_qualify_to_their_own_domain_not_a_siblings(self):
        """Resolution row `sibling-only`: the ref qualifies to its OWN domain even when only a sibling
        declares the code — every controller kind, since branches and batch refs are the ones a
        hand-written pass forgets.

        This crate is the authored shape that used to work by falling through to another domain. It
        now produces refs naming pipes that do not exist, and that is the intended answer: the ref was
        never resolvable under the rule, and dependency validation is where the user is told so. The
        fixture needs two domains to say anything at all — in a single-domain crate, owner-domain
        qualification and the deleted crate-wide search agree on every input.
        """
        result = normalize_crate(_cross_domain_crate(), mthds_version=MTHDS_TEST_VERSION)
        sequence = result.pipes["orchestrator.run_all"]
        assert isinstance(sequence, PipeSequenceBlueprint)
        assert sequence.steps[0].pipe == "orchestrator.present_as_markdown"

        parallel = result.pipes["orchestrator.fan_out"]
        assert isinstance(parallel, PipeParallelBlueprint)
        assert [branch.pipe for branch in parallel.branches] == ["orchestrator.present_as_markdown", "orchestrator.render_html"]

        condition = result.pipes["orchestrator.route"]
        assert isinstance(condition, PipeConditionBlueprint)
        assert condition.outcomes == {"markdown": "orchestrator.present_as_markdown"}
        assert condition.default_outcome == "orchestrator.render_html"

        batch = result.pipes["orchestrator.batch_all"]
        assert isinstance(batch, PipeBatchBlueprint)
        assert batch.branch_pipe_code == "orchestrator.present_as_markdown"

        # The sibling's own pipes are untouched: qualification is per declaring pipe, not global.
        assert "presentation.present_as_markdown" in result.pipes

    def test_own_domain_ref_resolves(self):
        """Resolution row `own-only`: a bare ref to a pipe the owner domain declares still resolves,
        and the resulting crate is closed over it.
        """
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        pipeline = result.pipes["scoring.pipeline"]
        assert isinstance(pipeline, PipeSequenceBlueprint)
        assert pipeline.steps[0].pipe == "scoring.compute_score"
        assert "scoring.compute_score" in result.pipes

    def test_special_outcomes_are_left_alone(self):
        """`fail` / `continue` are outcomes, not pipe refs — they must survive un-qualified."""
        result = normalize_crate(_cross_domain_crate(), mthds_version=MTHDS_TEST_VERSION)
        condition = result.pipes["orchestrator.route_to_special"]
        assert isinstance(condition, PipeConditionBlueprint)
        assert condition.outcomes == {"stop": SpecialOutcome.FAIL}
        assert condition.default_outcome == SpecialOutcome.CONTINUE

    def test_own_domain_wins_when_two_domains_declare_the_code(self):
        """Resolution row `both-declare`: the owner's own pipe, with no ambiguity error.

        Ambiguity was a *consequence* of searching. Nothing is searched for now, so a second domain
        declaring the same code is simply irrelevant to how the first domain's refs resolve — which is
        the contextual stability this rule buys: installing or writing an unrelated `present_as_markdown`
        elsewhere cannot change what an existing pipe means.
        """
        crate = _cross_domain_crate()
        crate.pipes["orchestrator.present_as_markdown"] = PipeLLMBlueprint(
            description="The orchestrator's own presenter",
            inputs={"data": "Text"},
            output="Text",
            prompt="Present $data",
        )
        result = normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)
        sequence = result.pipes["orchestrator.run_all"]
        assert isinstance(sequence, PipeSequenceBlueprint)
        assert sequence.steps[0].pipe == "orchestrator.present_as_markdown"

    def test_bare_pipe_ref_matching_nothing_is_qualified_not_raised(self):
        """Resolution row `nowhere`: the pass qualifies and moves on; it does not check existence.

        It cannot: it sees one load batch, and a batch may legitimately reference a pipe a prior batch
        put in the same domain (a `-L` directory, a secondary load). Only dependency validation, which
        sees the whole live library, can tell a forward reference from a typo.
        """
        crate = LibraryCrate(
            pipes={
                "orchestrator.run_all": PipeSequenceBlueprint(
                    description="Calls a pipe that is not in the crate",
                    output="Text",
                    steps=[SubPipeBlueprint(pipe="nowhere_to_be_found")],
                ),
            },
            domains={"orchestrator": DomainBlueprint(code="orchestrator", description="Orchestrator domain")},
        )
        result = normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)
        sequence = result.pipes["orchestrator.run_all"]
        assert isinstance(sequence, PipeSequenceBlueprint)
        assert sequence.steps[0].pipe == "orchestrator.nowhere_to_be_found"

    def test_refinement_with_structured_base_is_flattened(self):
        """Refining a concept with a structure adopts that (qualified) structure and drops `refines`."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        detailed = result.concepts["scoring.DetailedScore"]
        assert isinstance(detailed, ConceptBlueprint)
        assert detailed.refines is None
        assert isinstance(detailed.structure, dict)
        assert set(detailed.structure.keys()) == {"value", "label", "note"}
        # The adopted structure carries the base's already-qualified refs.
        assert _structure_field(detailed, "label").concept_ref == "scoring.Category"
        assert _structure_field(detailed, "note").concept_ref == "native.Text"

    def test_refinement_with_structureless_native_base_keeps_refines(self):
        """Refining a structureless native (Date) keeps a qualified `refines` and stays structureless."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        custom_date = result.concepts["scoring.CustomDate"]
        assert isinstance(custom_date, ConceptBlueprint)
        assert custom_date.refines == "native.Date"
        assert custom_date.structure is None

    def test_refinement_with_structured_native_base_keeps_refines(self):
        """Refining a STRUCTURED native (Text) keeps the qualified `refines` and is NOT flattened (B1-2).

        The old behavior inlined native.Text's `text` field and dropped `refines`, which loses the
        native content class on round-trip. The native is materialized separately (step 4), so keeping
        the link is both sufficient and identity-preserving.
        """
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        summary = result.concepts["scoring.Summary"]
        assert isinstance(summary, ConceptBlueprint)
        assert summary.refines == "native.Text"
        assert summary.structure is None
        # The native base it points at is materialized in the crate (so the link resolves).
        assert "native.Text" in result.concepts

    def test_multi_hop_native_backed_chain_keeps_refines(self):
        """A concept whose refinement chain reaches a native only through an intermediate keeps `refines`."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        long_summary = result.concepts["scoring.LongSummary"]
        assert isinstance(long_summary, ConceptBlueprint)
        # Not flattened: the chain LongSummary -> Summary -> native.Text bottoms at a native.
        assert long_summary.refines == "scoring.Summary"
        assert long_summary.structure is None

    def test_referenced_natives_are_materialized(self):
        """Every referenced native is materialized as a `native.<Code>` concept entry."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        # native.Text is referenced by a structure field (and pipe io); it materializes WITH a structure.
        text_native = result.concepts["native.Text"]
        assert isinstance(text_native, ConceptBlueprint)
        assert isinstance(text_native.structure, dict)
        assert "text" in text_native.structure
        # native.Date is referenced via a `refines`; it materializes from the pinned definitions
        # with its declared structure (a required `date` plus an optional `time` field).
        date_native = result.concepts["native.Date"]
        assert isinstance(date_native, ConceptBlueprint)
        assert isinstance(date_native.structure, dict)
        assert set(date_native.structure.keys()) == {"date", "time"}

    def test_unreferenced_natives_absent(self):
        """Natives that nothing references are not materialized into the crate."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        assert "native.SearchResult" not in result.concepts
        assert "native.Page" not in result.concepts

    def test_fingerprint_recomputed_and_version_stamped(self):
        """The normalized crate carries the D2-scope fingerprint and the mthds_version stamp."""
        result = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        assert result.mthds_version == MTHDS_TEST_VERSION
        assert result.fingerprint != ""
        assert result.fingerprint == result.compute_normalized()

    def test_normalization_is_idempotent(self):
        """Normalizing an already-normalized crate is a fixed point (content and fingerprint)."""
        once = normalize_crate(_authored_crate(), mthds_version=MTHDS_TEST_VERSION)
        twice = normalize_crate(once, mthds_version=MTHDS_TEST_VERSION)
        assert twice.fingerprint == once.fingerprint
        assert twice.concepts == once.concepts
        assert twice.pipes == once.pipes
        assert twice.domains == once.domains

    def test_deep_reverse_refinement_chain_flattens_without_recursion(self):
        result = normalize_crate(_reverse_refinement_chain_crate(1_500), mthds_version=MTHDS_TEST_VERSION)

        first = result.concepts["scale.Node0000"]
        assert isinstance(first, ConceptBlueprint)
        assert first.refines is None
        assert isinstance(first.structure, dict)
        assert set(first.structure) == {"value"}

    def test_refinement_resolution_work_is_linear_in_chain_length(self, mocker: MockerFixture):
        chain_size = 400
        native_check = mocker.spy(NativeConceptCode, "is_native_concept_ref_or_code")

        normalize_crate(_reverse_refinement_chain_crate(chain_size), mthds_version=MTHDS_TEST_VERSION)

        assert native_check.call_count < chain_size * 10

    def test_refinement_cycle_has_explicit_diagnostic(self):
        crate = LibraryCrate(
            concepts={
                "cycle.A": ConceptBlueprint(description="A", refines="B"),
                "cycle.B": ConceptBlueprint(description="B", refines="C"),
                "cycle.C": ConceptBlueprint(description="C", refines="A"),
            },
        )

        with pytest.raises(CrateNormalizationError) as exc_info:
            normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)

        assert str(exc_info.value) == "Refinement cycle detected: cycle.A -> cycle.B -> cycle.C -> cycle.A"

    def test_non_domain_qualified_key_raises(self):
        """A crate key that is not domain-qualified is a contract violation, surfaced explicitly."""
        crate = LibraryCrate(concepts={"BareConcept": "a concept with no domain in its key"})
        with pytest.raises(CrateNormalizationError, match="not domain-qualified"):
            normalize_crate(crate, mthds_version=MTHDS_TEST_VERSION)
