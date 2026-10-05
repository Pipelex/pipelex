from typing import TYPE_CHECKING

from pipelex.libraries.library_manager import reachable_dependency_pipe_refs
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

if TYPE_CHECKING:
    from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion

ALIAS = "github.com/invented/alpha-lib/alpha"


def _leaf(*, description: str) -> PipeLLMBlueprint:
    return PipeLLMBlueprint(description=description, inputs={"data": "Text"}, output="Text", prompt="use $data")


def _sequence(*step_refs: str) -> PipeSequenceBlueprint:
    return PipeSequenceBlueprint(description="seq", output="Text", steps=[SubPipeBlueprint(pipe=step_ref) for step_ref in step_refs])


class TestDependencyPipeReachability:
    """The pipes a dependency loads are its public ones and whatever they reach through the package's own references."""

    def test_every_controller_kind_is_followed_across_several_hops(self):
        pipes: dict[str, PipeBlueprintUnion] = {
            "alpha.entry": _sequence(f"{ALIAS}->alpha.router"),
            "alpha.router": PipeConditionBlueprint(
                description="route",
                inputs={"data": "Text"},
                output="Text",
                expression="data",
                outcomes={"fan": f"{ALIAS}->alpha.fan", "stop": SpecialOutcome.FAIL},
                default_outcome=f"{ALIAS}->alpha.fallback",
            ),
            "alpha.fan": PipeParallelBlueprint(
                description="fan",
                output="Composite",
                branches=[SubPipeBlueprint(pipe=f"{ALIAS}->alpha.batched", result="one")],
            ),
            "alpha.batched": PipeBatchBlueprint(
                description="batch",
                inputs={"items": "Text[]"},
                output="Text[]",
                branch_pipe_code=f"{ALIAS}->alpha.leaf",
                input_list_name="items",
                input_item_name="item",
            ),
            "alpha.fallback": _leaf(description="fallback"),
            "alpha.leaf": _leaf(description="leaf"),
            "alpha.orphan": _leaf(description="orphan"),
        }

        reachable = reachable_dependency_pipe_refs(public_pipe_refs={"alpha.entry"}, qualified_pipes=pipes, package_alias=ALIAS)

        assert reachable == {"alpha.entry", "alpha.router", "alpha.fan", "alpha.batched", "alpha.fallback", "alpha.leaf"}

    def test_a_cycle_terminates(self):
        pipes: dict[str, PipeBlueprintUnion] = {
            "alpha.ping": _sequence(f"{ALIAS}->alpha.pong"),
            "alpha.pong": _sequence(f"{ALIAS}->alpha.ping", f"{ALIAS}->alpha.leaf"),
            "alpha.leaf": _leaf(description="leaf"),
        }

        reachable = reachable_dependency_pipe_refs(public_pipe_refs={"alpha.ping"}, qualified_pipes=pipes, package_alias=ALIAS)

        assert reachable == {"alpha.ping", "alpha.pong", "alpha.leaf"}

    def test_a_ref_without_its_domain_reaches_every_pipe_of_that_code(self):
        """`alias->leaf` resolves by code within the package; where two domains declare it, both are kept for lookup to refuse."""
        pipes: dict[str, PipeBlueprintUnion] = {
            "alpha.entry": _sequence(f"{ALIAS}->leaf"),
            "alpha.leaf": _leaf(description="alpha leaf"),
            "beta.leaf": _leaf(description="beta leaf"),
            "beta.other": _leaf(description="unreached"),
        }

        reachable = reachable_dependency_pipe_refs(public_pipe_refs={"alpha.entry"}, qualified_pipes=pipes, package_alias=ALIAS)

        assert reachable == {"alpha.entry", "alpha.leaf", "beta.leaf"}

    def test_refs_outside_the_package_or_to_undeclared_pipes_are_not_followed(self):
        pipes: dict[str, PipeBlueprintUnion] = {
            "alpha.entry": _sequence("other->alpha.leaf", f"{ALIAS}->alpha.missing", f"{ALIAS}->missing"),
            "alpha.leaf": _leaf(description="leaf"),
        }

        reachable = reachable_dependency_pipe_refs(public_pipe_refs={"alpha.entry", "alpha.not_declared"}, qualified_pipes=pipes, package_alias=ALIAS)

        assert reachable == {"alpha.entry"}

    def test_a_ref_without_its_domain_follows_only_the_exported_match_when_there_is_one(self):
        """Lookup resolves `alias->x` to the exported `alpha.x`, so the private `beta.x` is never reached, nor built."""
        pipes: dict[str, PipeBlueprintUnion] = {
            "alpha.entry": _sequence(f"{ALIAS}->x"),
            "alpha.x": _leaf(description="exported x"),
            "beta.x": _sequence(f"{ALIAS}->beta.missing"),
        }

        reachable = reachable_dependency_pipe_refs(public_pipe_refs={"alpha.entry", "alpha.x"}, qualified_pipes=pipes, package_alias=ALIAS)

        assert reachable == {"alpha.entry", "alpha.x"}
