from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.pipe_controllers.pipe_condition import PipeCondition, PipeConditionPipeMap


class TestPipeConditionValidation:
    """Tests for PipeCondition validate_inputs method"""

    def test_pipe_condition_creation(self):
        """Test basic PipeCondition creation"""
        pipe_condition = PipeCondition(
            domain="test_domain",
            code="test_condition",
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain="test_domain", blueprint={"input_var": InputRequirementBlueprint(concept_code="Text")}
            ),
            output=ConceptFactory.make(
                concept_code="ProcessedText", domain="test_domain", definition="Processed text", structure_class_name="ProcessedText"
            ),
            expression="input_var",
            pipe_map=[
                PipeConditionPipeMap(expression_result="value1", pipe_code="pipe_a"),
                PipeConditionPipeMap(expression_result="value2", pipe_code="pipe_b"),
            ],
            default_pipe_code="default_pipe",
        )

        assert pipe_condition.code == "test_condition"
        assert pipe_condition.domain == "test_domain"
        assert len(pipe_condition.pipe_map) == 2
        assert pipe_condition.expression == "input_var"
        assert pipe_condition.default_pipe_code == "default_pipe"

    def test_pipe_condition_expression_template_vs_expression(self):
        """Test that both expression_template and expression formats work"""
        # Test with expression_template
        pipe_condition_template = PipeCondition(
            domain="test_domain",
            code="test_condition_template",
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain="test_domain", blueprint={"var": InputRequirementBlueprint(concept_code="test_domain.Text")}
            ),
            output=ConceptFactory.make(concept_code="Result", domain="test_domain", definition="Result", structure_class_name="Result"),
            expression_template="{{ var }}",
            pipe_map=[PipeConditionPipeMap(expression_result="value", pipe_code="target_pipe")],
        )

        # Test with expression
        pipe_condition_expr = PipeCondition(
            domain="test_domain",
            code="test_condition_expr",
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain="test_domain", blueprint={"var": InputRequirementBlueprint(concept_code="test_domain.Text")}
            ),
            output=ConceptFactory.make(concept_code="Result", domain="test_domain", definition="Result", structure_class_name="Result"),
            expression="var",
            pipe_map=[PipeConditionPipeMap(expression_result="value", pipe_code="target_pipe")],
        )

        # Both should have the same applied expression template format
        assert pipe_condition_template.applied_expression_template == "{{ var }}"
        assert pipe_condition_expr.applied_expression_template == "{{ var }}"
