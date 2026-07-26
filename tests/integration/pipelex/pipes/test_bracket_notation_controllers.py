from typing import Callable

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.method_hub import get_concept_library
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint


class TestBracketNotationInControllers:
    """Test that controller factories correctly handle bracket notation in inputs and outputs."""

    def test_pipe_parallel_with_bracket_notation(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeParallel factory with bracket notation."""
        domain_code = "test"
        concept_library = get_concept_library()

        concept_data_item = ConceptFactory.make_from_blueprint(
            concept_code="DataItem",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Data item"),
        )
        concept_library.add_concepts([concept_data_item])
        concept_processed_data = ConceptFactory.make_from_blueprint(
            concept_code="ProcessedData",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Processed data"),
        )
        concept_library.add_concepts([concept_processed_data])

        blueprint = PipeParallelBlueprint(
            description="Process items in parallel",
            inputs={"data": "DataItem[2]"},
            output="ProcessedData",
            branches=[],
            add_each_output=True,
        )

        pipe = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_parallel",
            blueprint=blueprint,
            concept_codes_from_the_same_domain=[concept_data_item.code, concept_processed_data.code],
        )

        assert pipe.inputs.root["data"].multiplicity == 2
        assert pipe.output.concept.code == "ProcessedData"

        concept_library.teardown()

    def test_pipe_condition_with_bracket_notation(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeCondition factory with bracket notation."""
        domain_code = "test"
        concept_library = get_concept_library()

        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="Category",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Category"),
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="Result",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Result"),
        )
        concept_library.add_concepts([concept_1, concept_2])

        blueprint = PipeConditionBlueprint(
            description="Route based on category",
            inputs={"items": "Category[]"},
            output="Result?",
            expression="items",
            outcomes={"A": "pipe_a"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=blueprint,
            concept_codes_from_the_same_domain=[concept_1.code, concept_2.code],
        )

        assert pipe.inputs.root["items"].multiplicity is True
        assert pipe.output.concept.code == "Result"

        concept_library.teardown()

    def test_pipe_batch_with_bracket_notation(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        """Test PipeBatch factory with bracket notation."""
        domain_code = "test"
        concept_library = get_concept_library()

        concept_item = ConceptFactory.make_from_blueprint(
            concept_code="Item",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Item"),
        )
        concept_processed_item = ConceptFactory.make_from_blueprint(
            concept_code="ProcessedItem",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Processed item"),
        )
        concept_library.add_concepts([concept_item, concept_processed_item])

        blueprint = PipeBatchBlueprint(
            description="Batch process items",
            inputs={"items": "Item[]"},
            output="ProcessedItem[]",
            branch_pipe_code="process_single",
            input_list_name="items",
            input_item_name="item",
        )

        pipe = PipeFactory[PipeBatch].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_batch",
            blueprint=blueprint,
            concept_codes_from_the_same_domain=[concept_item.code, concept_processed_item.code],
        )

        assert pipe.inputs.root["items"].multiplicity is True
        assert pipe.output.concept.code == "ProcessedItem"

        concept_library.teardown()
