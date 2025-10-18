"""Integration tests for bracket notation in controller pipe factories."""

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.hub import get_concept_library
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_factory import PipeBatchFactory
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_factory import PipeConditionFactory
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_factory import PipeParallelFactory


class TestBracketNotationInControllers:
    """Test that controller factories correctly handle bracket notation in inputs and outputs."""

    def test_pipe_parallel_with_bracket_notation(self):
        """Test PipeParallel factory with bracket notation."""
        domain = "test"
        concept_library = get_concept_library()

        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="DataItem",
            domain=domain,
            blueprint=ConceptBlueprint(description="Data item"),
            concept_codes_from_the_same_domain=["DataItem"],
        )
        concept_library.add_concepts([concept_1])

        blueprint = PipeParallelBlueprint(
            description="Process items in parallel",
            inputs={"data": "DataItem[2]"},
            output="ProcessedData",
            parallels=[],
            add_each_output=True,
        )

        pipe = PipeParallelFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_parallel",
            blueprint=blueprint,
        )

        assert pipe.inputs.root["data"].multiplicity == 2
        assert pipe.output.code == "ProcessedData"

        concept_library.teardown()

    def test_pipe_condition_with_bracket_notation(self):
        """Test PipeCondition factory with bracket notation."""
        domain = "test"
        concept_library = get_concept_library()

        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="Category",
            domain=domain,
            blueprint=ConceptBlueprint(description="Category"),
            concept_codes_from_the_same_domain=["Category"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="Result",
            domain=domain,
            blueprint=ConceptBlueprint(description="Result"),
            concept_codes_from_the_same_domain=["Result"],
        )
        concept_library.add_concepts([concept_1, concept_2])

        blueprint = PipeConditionBlueprint(
            description="Route based on category",
            inputs={"items": "Category[]"},
            output="Result",
            expression="items",
            outcomes={"A": "pipe_a"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe = PipeConditionFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_condition",
            blueprint=blueprint,
        )

        assert pipe.inputs.root["items"].multiplicity is True
        assert pipe.output.code == "Result"

        concept_library.teardown()

    def test_pipe_batch_with_bracket_notation(self):
        """Test PipeBatch factory with bracket notation."""
        domain = "test"
        concept_library = get_concept_library()

        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="Item",
            domain=domain,
            blueprint=ConceptBlueprint(description="Item"),
            concept_codes_from_the_same_domain=["Item"],
        )
        concept_library.add_concepts([concept_1])

        blueprint = PipeBatchBlueprint(
            description="Batch process items",
            inputs={"items": "Item[]"},
            output="ProcessedItem[]",
            branch_pipe_code="process_single",
            input_list_name="items",
            input_item_name="item",
        )

        pipe = PipeBatchFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_batch",
            blueprint=blueprint,
        )

        assert pipe.inputs.root["items"].multiplicity is True
        assert pipe.output.code == "ProcessedItem"

        concept_library.teardown()
