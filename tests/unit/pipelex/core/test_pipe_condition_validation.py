from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.pipe_controllers.pipe_condition import PipeCondition


class TestPipeConditionValidation:
    """Tests for PipeCondition validate_inputs method"""

    def test_pipe_condition_creation(self):
        """Test basic PipeCondition creation"""
        pipe_condition = PipeCondition(
            domain="test_domain",
            code="test_condition",
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"input_var": "test_domain.Text"}),
            output_concept_code="test_domain.ProcessedText",
            expression="input_var",
            pipe_map={"value1": "pipe_a", "value2": "pipe_b"},
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
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"var": "test_domain.Text"}),
            output_concept_code="test_domain.Result",
            expression_template="{{ var }}",
            pipe_map={"value": "target_pipe"},
        )

        # Test with expression
        pipe_condition_expr = PipeCondition(
            domain="test_domain",
            code="test_condition_expr",
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"var": "test_domain.Text"}),
            output_concept_code="test_domain.Result",
            expression="var",
            pipe_map={"value": "target_pipe"},
        )

        # Both should have the same applied expression template format
        assert pipe_condition_template.applied_expression_template == "{{ var }}"
        assert pipe_condition_expr.applied_expression_template == "{{ var }}"
