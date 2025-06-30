from unittest.mock import Mock, patch

from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.pipe_controllers.pipe_condition import PipeCondition


class TestPipeConditionValidation:
    """Tests for PipeCondition validate_inputs method"""

    def test_pipe_condition_validate_inputs_basic(self):
        """Test basic input validation for a simple PipeCondition"""
        # Create a simple PipeCondition with proper inputs
        pipe_condition = PipeCondition(
            domain="test_domain",
            code="test_condition",
            inputs=PipeInputSpec(root={"input_var": "test_domain.Text"}),
            output_concept_code="test_domain.ProcessedText",
            expression="input_var",
            pipe_map={"value1": "pipe_a", "value2": "pipe_b"},
            default_pipe_code="default_pipe",
        )

        # The validate_inputs method should run without error
        # since it's called during model validation
        assert pipe_condition.code == "test_condition"
        assert pipe_condition.domain == "test_domain"
        assert len(pipe_condition.pipe_map) == 2

    @patch("pipelex.pipe_controllers.pipe_condition.get_required_pipe")
    def test_pipe_condition_needed_inputs_with_mocked_pipes(self, mock_get_pipe: Mock):
        """Test needed_inputs calculation with mocked pipe dependencies"""

        # Set up the mock to return different pipes based on pipe_code
        def mock_get_pipe_side_effect(pipe_code: str):
            if pipe_code == "pipe_a":
                # Mock pipe that needs "color"
                mock_pipe = Mock()
                mock_pipe.inputs = PipeInputSpec(root={"color": "test_domain.Color"})
                del mock_pipe.needed_inputs
                return mock_pipe
            elif pipe_code == "pipe_b":
                # Mock pipe that needs "size"
                mock_pipe = Mock()
                mock_pipe.inputs = PipeInputSpec(root={"size": "test_domain.Size"})
                del mock_pipe.needed_inputs
                return mock_pipe
            elif pipe_code == "default_pipe":
                # Mock default pipe that needs "name"
                mock_pipe = Mock()
                mock_pipe.inputs = PipeInputSpec(root={"name": "test_domain.Name"})
                del mock_pipe.needed_inputs
                return mock_pipe
            else:
                raise Exception(f"Unknown pipe: {pipe_code}")

        mock_get_pipe.side_effect = mock_get_pipe_side_effect

        # Create PipeCondition that uses an expression variable and has multiple target pipes
        pipe_condition = PipeCondition(
            domain="test_domain",
            code="test_condition",
            inputs=PipeInputSpec(
                root={
                    "condition_var": "test_domain.Text",  # for the expression
                    "color": "test_domain.Color",  # for pipe_a
                    "size": "test_domain.Size",  # for pipe_b
                    "name": "test_domain.Name",  # for default_pipe
                }
            ),
            output_concept_code="test_domain.Result",
            expression="condition_var",  # This will need condition_var as input
            pipe_map={"option_a": "pipe_a", "option_b": "pipe_b"},
            default_pipe_code="default_pipe",
        )

        # Test needed_inputs calculation
        needed_inputs = pipe_condition.needed_inputs()

        # Should need: condition_var (for expression) + color (pipe_a) + size (pipe_b) + name (default_pipe)
        assert "condition_var" in needed_inputs.root
        assert "color" in needed_inputs.root
        assert "size" in needed_inputs.root
        assert "name" in needed_inputs.root
        assert len(needed_inputs.root) == 4

    def test_pipe_condition_expression_template_vs_expression(self):
        """Test that both expression_template and expression formats work"""
        # Test with expression_template (note: no expression field)
        pipe_condition_template = PipeCondition(
            domain="test_domain",
            code="test_condition_template",
            inputs=PipeInputSpec(root={"var": "test_domain.Text"}),
            output_concept_code="test_domain.Result",
            expression_template="{{ var }}",
            pipe_map={"value": "target_pipe"},
        )

        # Test with expression (note: no expression_template field)
        pipe_condition_expr = PipeCondition(
            domain="test_domain",
            code="test_condition_expr",
            inputs=PipeInputSpec(root={"var": "test_domain.Text"}),
            output_concept_code="test_domain.Result",
            expression="var",
            pipe_map={"value": "target_pipe"},
        )

        # Both should have the same applied expression template format
        assert pipe_condition_template.applied_expression_template == "{{ var }}"
        assert pipe_condition_expr.applied_expression_template == "{{ var }}"
