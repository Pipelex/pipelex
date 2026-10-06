from pipelex.libraries.crate_qualification import qualify_crate
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from tests.unit.pipelex.libraries.test_data import CrateQualificationTestData


class TestCrateQualificationUnderAPackageAlias:
    """With `package_alias`, a dependency's own pipe refs become the key the consumer's library holds them under.

    A dependency's pipes are registered in the consumer's library as `alias->domain.code`, and every reader of a
    sub-pipe ref looks it up there. So a ref the package wrote must be stored in that form, or it finds nothing, or
    it finds the consumer's own pipe of the same `domain.code`.
    """

    ALIAS = "github.com/invented/alpha-lib/alpha"

    def _qualified_pipes(self) -> dict[str, object]:
        crate = CrateQualificationTestData.crate()
        crate.pipes["alpha.route_special"] = PipeConditionBlueprint(
            description="route to a special outcome",
            inputs={"data": "Category"},
            output="Report",
            expression="x",
            outcomes={"stop": SpecialOutcome.FAIL, "hit": "leaf"},
            default_outcome="leaf",
        )
        crate.pipes["alpha.calls_other_package"] = PipeSequenceBlueprint(
            description="calls a package of its own",
            output="Text",
            steps=[SubPipeBlueprint(pipe="other->beta.helper")],
        )
        return dict(qualify_crate(crate, package_alias=self.ALIAS).pipes)

    def test_every_controller_kind_is_aliased(self):
        pipes = self._qualified_pipes()
        aliased_leaf = f"{self.ALIAS}->alpha.leaf"

        sequence = pipes["alpha.seq"]
        assert isinstance(sequence, PipeSequenceBlueprint)
        assert sequence.pipe_steps[0].pipe == aliased_leaf
        parallel = pipes["alpha.par"]
        assert isinstance(parallel, PipeParallelBlueprint)
        assert parallel.branches[0].pipe == aliased_leaf
        condition = pipes["alpha.cond"]
        assert isinstance(condition, PipeConditionBlueprint)
        assert condition.outcomes == {"hit": aliased_leaf}
        assert condition.default_outcome == aliased_leaf
        batch = pipes["alpha.batched"]
        assert isinstance(batch, PipeBatchBlueprint)
        assert batch.branch_pipe_code == aliased_leaf

    def test_concept_refs_are_not_aliased(self):
        """Only pipe refs move: a dependency's concepts are bound at construction, under their `domain.Code`."""
        leaf = self._qualified_pipes()["alpha.leaf"]
        assert isinstance(leaf, PipeLLMBlueprint)
        assert leaf.output == "alpha.Report"

    def test_special_outcomes_and_already_aliased_refs_are_left_alone(self):
        pipes = self._qualified_pipes()
        condition = pipes["alpha.route_special"]
        assert isinstance(condition, PipeConditionBlueprint)
        assert condition.outcomes == {"stop": SpecialOutcome.FAIL, "hit": f"{self.ALIAS}->alpha.leaf"}
        other = pipes["alpha.calls_other_package"]
        assert isinstance(other, PipeSequenceBlueprint)
        assert other.pipe_steps[0].pipe == "other->beta.helper"

    def test_is_idempotent(self):
        once = qualify_crate(CrateQualificationTestData.crate(), package_alias=self.ALIAS)
        twice = qualify_crate(
            CrateQualificationTestData.crate().model_copy(update={"concepts": once.concepts, "pipes": once.pipes}), package_alias=self.ALIAS
        )
        assert twice.pipes == once.pipes
        sequence = twice.pipes["alpha.seq"]
        assert isinstance(sequence, PipeSequenceBlueprint)
        assert sequence.pipe_steps[0].pipe == f"{self.ALIAS}->alpha.leaf"
