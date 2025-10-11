from pipelex.core.concepts.concept_factory import ConceptBlueprint, ConceptFactory
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.hub import get_concept_provider
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_factory import PipeConditionFactory


class TestPipeConditionValidation:
    """Tests for PipeCondition validate_inputs method"""

    def test_pipe_condition_creation(self):
        """Test basic PipeCondition creation"""
        domain = "test_domain"
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["TestConcept"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="Result",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["Result"],
        )
        concept_library = get_concept_provider()
        concept_library.add_concepts([concept_1, concept_2])

        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Test condition for validation",
            inputs={"input_var": InputRequirementBlueprint(concept=concept_1.concept_string)},
            output=concept_2.concept_string,
            expression="input_var",
            pipe_map={"value1": "pipe_a", "value2": "pipe_b"},
            default_pipe_code="default_pipe",
        )

        pipe_condition = PipeConditionFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_condition",
            blueprint=pipe_condition_blueprint,
        )

        assert pipe_condition.code == "test_condition"
        assert pipe_condition.domain == domain
        assert len(pipe_condition.pipe_map) == 2
        assert pipe_condition.expression == "input_var"
        assert pipe_condition.default_pipe_code == "default_pipe"

        concept_library.teardown()

    def test_pipe_condition_expression_template_vs_expression(self):
        """Test that both expression_template and expression formats work"""
        # Test with expression_template
        domain = "test_domain"
        concept_library = get_concept_provider()
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="TestConcept",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["TestConcept"],
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="Result",
            domain=domain,
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["Result"],
        )
        concept_library.add_concepts([concept_1, concept_2])

        pipe_condition_template_blueprint = PipeConditionBlueprint(
            description="Test condition with expression template",
            inputs={"var": InputRequirementBlueprint(concept=concept_1.concept_string)},
            output=concept_2.concept_string,
            expression_template="{{ var }}",
            pipe_map={"value": "target_pipe"},
        )

        pipe_condition_template = PipeConditionFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_condition_template",
            blueprint=pipe_condition_template_blueprint,
        )

        # Test with expression
        pipe_condition_expr_blueprint = PipeConditionBlueprint(
            description="Test condition with expression",
            inputs={"var": InputRequirementBlueprint(concept=concept_1.concept_string)},
            output=concept_2.concept_string,
            expression="var",
            pipe_map={"value": "target_pipe"},
        )

        pipe_condition_expr = PipeConditionFactory.make_from_blueprint(
            domain=domain,
            pipe_code="test_condition_expr",
            blueprint=pipe_condition_expr_blueprint,
        )

        # Both should have the same applied expression template format
        assert pipe_condition_template.applied_expression_template == "{{ var }}"
        assert pipe_condition_expr.applied_expression_template == "{{ var }}"
        concept_library.teardown()
