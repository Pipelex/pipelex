from pathlib import Path
from typing import Callable

from pipelex.core.concepts.concept_factory import ConceptBlueprint, ConceptFactory
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_machinery.pipe_factory import PipeFactory


class TestPipeConditionValidation:
    """Tests for PipeCondition validate_inputs method"""

    def test_pipe_condition_creation(self, load_test_library: Callable[[list[Path]], None]):
        """Test basic PipeCondition creation"""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        domain_code = "test_domain"
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="Result",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )
        concept_library = get_concept_library()
        concept_library.add_concepts([concept_1, concept_2])

        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Test condition for validation",
            inputs={"input_var": concept_1.concept_ref},
            output=concept_2.concept_ref,
            expression="input_var",
            outcomes={"value1": "pipe_a", "value2": "pipe_b"},
            default_outcome="default_pipe",
        )

        pipe_condition = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        assert pipe_condition.code == "test_condition"
        assert pipe_condition.domain_code == domain_code
        assert len(pipe_condition.outcome_map) == 2
        assert pipe_condition.expression == "{{ input_var }}"
        assert pipe_condition.default_outcome == "default_pipe"

        concept_library.teardown()

    def test_pipe_condition_expression_template_vs_expression(self, load_test_library: Callable[[list[Path]], None]):
        """Test that both expression_template and expression formats work"""
        load_test_library([Path("tests/integration/pipelex/pipes/controller/pipe_condition")])
        # Test with expression_template
        domain_code = "test_domain"
        concept_library = get_concept_library()
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="Result",
            domain_code=domain_code,
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )
        concept_library.add_concepts([concept_1, concept_2])

        pipe_condition_template_blueprint = PipeConditionBlueprint(
            description="Test condition with expression template",
            inputs={"var": concept_1.concept_ref},
            output=f"{concept_2.concept_ref}?",
            expression_template="{{ var }}",
            outcomes={"value": "target_pipe"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition_template = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition_template",
            blueprint=pipe_condition_template_blueprint,
        )

        # Test with expression
        pipe_condition_expr_blueprint = PipeConditionBlueprint(
            description="Test condition with expression",
            inputs={"var": concept_1.concept_ref},
            output=f"{concept_2.concept_ref}?",
            expression="var",
            outcomes={"value": "target_pipe"},
            default_outcome=SpecialOutcome.CONTINUE,
        )

        pipe_condition_expr = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=domain_code,
            pipe_code="test_condition_expr",
            blueprint=pipe_condition_expr_blueprint,
        )

        # Both should have the same applied expression template format
        assert pipe_condition_template.expression == "{{ var }}"
        assert pipe_condition_expr.expression == "{{ var }}"
        concept_library.teardown()
