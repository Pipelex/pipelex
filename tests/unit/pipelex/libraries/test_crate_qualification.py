"""Unit tests for `qualify_crate` — that it rewrites what it claims to, and only that.

The *resolution rule* (which pipe a bare ref resolves to when several domains declare the code, which
refs are left alone) is covered through `normalize_crate` in `test_crate_normalization.py` and stays
there. What lives here is the standalone pass's own contract: that every ref kind it advertises
actually comes back rewritten, that it does not touch its input, and that meeting it twice is the
same as meeting it once.

That first one is not a formality. A test module built around a fixture full of bare refs can assert
nothing about the *output* and still go green against a pass that does nothing at all — the envelope
looks right, the input is untouched, and two no-ops compare equal. Every test below reads a
qualified ref out of the result for that reason.
"""

import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_qualification import QualifiedCrateContent, qualify_crate
from pipelex.libraries.exceptions import CrateNormalizationError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


def _crate() -> LibraryCrate:
    """A crate carrying one bare ref of every kind the pass advertises."""
    return LibraryCrate(
        concepts={
            "alpha.Category": "a category",
            "alpha.Report": ConceptBlueprint(
                description="a report",
                structure={
                    "label": ConceptStructureBlueprint(
                        description="the label",
                        type=ConceptStructureBlueprintFieldType.CONCEPT,
                        concept_ref="Category",
                    ),
                    "tags": ConceptStructureBlueprint(
                        description="the tags",
                        type=ConceptStructureBlueprintFieldType.LIST,
                        item_type=ConceptStructureBlueprintFieldType.CONCEPT,
                        item_concept_ref="Category",
                    ),
                },
            ),
            "alpha.Detailed": ConceptBlueprint(description="a detailed report", refines="Report"),
        },
        pipes={
            "alpha.leaf": PipeLLMBlueprint(description="leaf", inputs={"item": "Category"}, output="Report", prompt="use $item"),
            "alpha.seq": PipeSequenceBlueprint(description="seq", output="Report", steps=[SubPipeBlueprint(pipe="leaf")]),
            "alpha.par": PipeParallelBlueprint(
                description="par",
                output="Composite",
                branches=[SubPipeBlueprint(pipe="leaf", result="one")],
            ),
            "alpha.cond": PipeConditionBlueprint(
                description="cond",
                output="Report",
                expression="x",
                outcomes={"hit": "leaf"},
                default_outcome="leaf",
            ),
            "alpha.batched": PipeBatchBlueprint(
                description="batch",
                inputs={"items": "Category[]"},
                output="Report[]",
                branch_pipe_code="leaf",
                input_list_name="items",
                input_item_name="item",
            ),
        },
        domains={"alpha": DomainBlueprint(code="alpha", description="alpha domain")},
    )


def _report_structure(result: QualifiedCrateContent) -> dict[str, ConceptStructureBlueprint]:
    report = result.concepts["alpha.Report"]
    assert isinstance(report, ConceptBlueprint)
    assert isinstance(report.structure, dict)
    return {name: field for name, field in report.structure.items() if isinstance(field, ConceptStructureBlueprint)}


class TestCrateQualification:
    # --- every ref kind the pass advertises, read back out of the result ---

    def test_concept_refines(self):
        detailed = qualify_crate(_crate()).concepts["alpha.Detailed"]
        assert isinstance(detailed, ConceptBlueprint)
        assert detailed.refines == "alpha.Report"

    def test_structure_field_refs(self):
        structure = _report_structure(qualify_crate(_crate()))
        assert structure["label"].concept_ref == "alpha.Category"
        assert structure["tags"].item_concept_ref == "alpha.Category"

    def test_pipe_io_refs(self):
        leaf = qualify_crate(_crate()).pipes["alpha.leaf"]
        assert leaf.inputs == {"item": "alpha.Category"}
        assert leaf.output == "alpha.Report"

    def test_multiplicity_markers_survive_qualification(self):
        batched = qualify_crate(_crate()).pipes["alpha.batched"]
        assert batched.inputs == {"items": "alpha.Category[]"}
        assert batched.output == "alpha.Report[]"

    def test_sequence_step_refs(self):
        sequence = qualify_crate(_crate()).pipes["alpha.seq"]
        assert isinstance(sequence, PipeSequenceBlueprint)
        assert [step.pipe for step in sequence.steps] == ["alpha.leaf"]

    def test_parallel_branch_refs(self):
        parallel = qualify_crate(_crate()).pipes["alpha.par"]
        assert isinstance(parallel, PipeParallelBlueprint)
        assert [branch.pipe for branch in parallel.branches] == ["alpha.leaf"]

    def test_condition_outcome_refs(self):
        condition = qualify_crate(_crate()).pipes["alpha.cond"]
        assert isinstance(condition, PipeConditionBlueprint)
        assert condition.outcomes == {"hit": "alpha.leaf"}
        assert condition.default_outcome == "alpha.leaf"

    def test_batch_branch_ref(self):
        batched = qualify_crate(_crate()).pipes["alpha.batched"]
        assert isinstance(batched, PipeBatchBlueprint)
        assert batched.branch_pipe_code == "alpha.leaf"

    def test_string_described_concept_passes_through(self):
        """A description holds no refs — it must come back as the same string, not a blueprint."""
        assert qualify_crate(_crate()).concepts["alpha.Category"] == "a category"

    # --- purity ---

    def test_input_crate_is_not_mutated(self):
        """The pass runs on a crate the caller still holds — in the library build, one it has cached."""
        crate = _crate()
        qualify_crate(crate)

        sequence = crate.pipes["alpha.seq"]
        assert isinstance(sequence, PipeSequenceBlueprint)
        assert sequence.steps[0].pipe == "leaf"
        assert crate.pipes["alpha.leaf"].output == "Report"
        detailed = crate.concepts["alpha.Detailed"]
        assert isinstance(detailed, ConceptBlueprint)
        assert detailed.refines == "Report"

    def test_is_idempotent(self):
        """Qualifying an already-qualified ref must be a no-op — `alpha.leaf` must not become
        `alpha.alpha.leaf`. The pass runs in more than one place, so a crate can meet it twice.
        """
        once = qualify_crate(_crate())
        twice = qualify_crate(_crate().model_copy(update={"concepts": once.concepts, "pipes": once.pipes}))
        assert twice.concepts == once.concepts
        assert twice.pipes == once.pipes
        # Anti-vacuity: two no-ops would also compare equal, so pin that the compared value is the
        # qualified one rather than whatever went in.
        second_pass_sequence = twice.pipes["alpha.seq"]
        assert isinstance(second_pass_sequence, PipeSequenceBlueprint)
        assert second_pass_sequence.steps[0].pipe == "alpha.leaf"

    # --- rejections, raised by the pass itself rather than through the normalizer ---

    @pytest.mark.parametrize(
        ("crate", "expected_message"),
        [
            pytest.param(
                LibraryCrate(concepts={"Bare": "an unqualified key"}),
                "not domain-qualified",
                id="unqualified-concept-key",
            ),
            pytest.param(
                LibraryCrate(pipes={"bare": PipeLLMBlueprint(description="bare", output="Text", prompt="go")}),
                "not domain-qualified",
                id="unqualified-pipe-key",
            ),
            pytest.param(
                LibraryCrate(
                    pipes={
                        "alpha.seq": PipeSequenceBlueprint(description="seq", output="Text", steps=[SubPipeBlueprint(pipe="ghost")]),
                    }
                ),
                "resolves to no pipe in the crate",
                id="unresolvable-bare-pipe-ref",
            ),
        ],
    )
    def test_rejects(self, crate: LibraryCrate, expected_message: str):
        """The pass raises on its own, not only through the normalizer that used to host it."""
        with pytest.raises(CrateNormalizationError, match=expected_message):
            qualify_crate(crate)
