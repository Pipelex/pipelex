from typing import Optional, Set
from unittest.mock import Mock, patch

from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.pipe_controllers.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sub_pipe import SubPipe


class TestPipeParallelValidation:
    """Tests for PipeParallel validate_inputs method"""

    def test_pipe_parallel_validate_inputs_basic(self):
        """Test basic input validation for a simple PipeParallel"""
        # Create a simple PipeParallel with proper inputs
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec(root={"input_var": "test_domain.Text"}),
            output_concept_code="test_domain.ProcessedText",
            parallel_sub_pipes=[SubPipe(pipe_code="test_pipe_1", output_name="result_1")],
            add_each_output=True,
            combined_output=None,
        )

        # The validate_inputs method should run without error
        # since it's called during model validation
        assert pipe_parallel.code == "test_parallel"
        assert pipe_parallel.domain == "test_domain"
        assert len(pipe_parallel.parallel_sub_pipes) == 1

    def test_pipe_parallel_needed_inputs_calculation(self):
        """Test that needed_inputs correctly calculates required inputs from all parallel pipes"""
        # This is a simplified test that demonstrates the concept
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec(root={"initial_input": "test_domain.Text"}),
            output_concept_code="test_domain.FinalOutput",
            parallel_sub_pipes=[SubPipe(pipe_code="step_1", output_name="step_1_output"), SubPipe(pipe_code="step_2", output_name="step_2_output")],
            add_each_output=True,
            combined_output=None,
        )

        # Test that the pipe parallel is created successfully
        assert pipe_parallel.code == "test_parallel"
        assert len(pipe_parallel.parallel_sub_pipes) == 2

        # The actual needed_inputs testing would require mocking the pipes
        # For now, we just verify the structure is correct
        assert pipe_parallel.inputs.root["initial_input"] == "test_domain.Text"

    @patch("pipelex.pipe_controllers.pipe_parallel.get_required_pipe")
    def test_pipe_parallel_needed_inputs_with_mocked_pipes(self, mock_get_pipe: Mock):
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
            elif pipe_code == "pipe_c":
                # Mock pipe that needs "name"
                mock_pipe = Mock()
                mock_pipe.inputs = PipeInputSpec(root={"name": "test_domain.Name"})
                del mock_pipe.needed_inputs
                return mock_pipe
            else:
                raise Exception(f"Unknown pipe: {pipe_code}")

        mock_get_pipe.side_effect = mock_get_pipe_side_effect

        # Create PipeParallel that runs multiple pipes in parallel
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec(
                root={
                    "color": "test_domain.Color",  # for pipe_a
                    "size": "test_domain.Size",  # for pipe_b
                    "name": "test_domain.Name",  # for pipe_c
                }
            ),
            output_concept_code="test_domain.Result",
            parallel_sub_pipes=[
                SubPipe(pipe_code="pipe_a", output_name="result_a"),
                SubPipe(pipe_code="pipe_b", output_name="result_b"),
                SubPipe(pipe_code="pipe_c", output_name="result_c"),
            ],
            add_each_output=True,
            combined_output=None,
        )

        # Test needed_inputs calculation
        needed_inputs = pipe_parallel.needed_inputs()

        # Should need: color (pipe_a) + size (pipe_b) + name (pipe_c)
        assert "color" in needed_inputs.root
        assert "size" in needed_inputs.root
        assert "name" in needed_inputs.root
        assert len(needed_inputs.root) == 3

    @patch("pipelex.pipe_controllers.pipe_parallel.get_required_pipe")
    def test_pipe_parallel_needed_inputs_with_overlapping_inputs(self, mock_get_pipe: Mock):
        """Test needed_inputs calculation when parallel pipes have overlapping input requirements"""

        # Set up the mock to return pipes with overlapping inputs
        def mock_get_pipe_side_effect(pipe_code: str):
            if pipe_code == "pipe_a":
                # Mock pipe that needs "text" and "color"
                mock_pipe = Mock()
                mock_pipe.inputs = PipeInputSpec(root={"text": "test_domain.Text", "color": "test_domain.Color"})
                del mock_pipe.needed_inputs
                return mock_pipe
            elif pipe_code == "pipe_b":
                # Mock pipe that needs "text" and "size" (overlapping "text" with pipe_a)
                mock_pipe = Mock()
                mock_pipe.inputs = PipeInputSpec(root={"text": "test_domain.Text", "size": "test_domain.Size"})
                del mock_pipe.needed_inputs
                return mock_pipe
            else:
                raise Exception(f"Unknown pipe: {pipe_code}")

        mock_get_pipe.side_effect = mock_get_pipe_side_effect

        # Create PipeParallel
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec(
                root={
                    "text": "test_domain.Text",  # shared by both pipes
                    "color": "test_domain.Color",  # for pipe_a
                    "size": "test_domain.Size",  # for pipe_b
                }
            ),
            output_concept_code="test_domain.Result",
            parallel_sub_pipes=[
                SubPipe(pipe_code="pipe_a", output_name="result_a"),
                SubPipe(pipe_code="pipe_b", output_name="result_b"),
            ],
            add_each_output=True,
            combined_output=None,
        )

        # Test needed_inputs calculation
        needed_inputs = pipe_parallel.needed_inputs()

        # Should need: text (both pipes) + color (pipe_a) + size (pipe_b)
        assert "text" in needed_inputs.root
        assert "color" in needed_inputs.root
        assert "size" in needed_inputs.root
        assert len(needed_inputs.root) == 3

    @patch("pipelex.pipe_controllers.pipe_parallel.get_required_pipe")
    def test_pipe_parallel_needed_inputs_with_batching(self, mock_get_pipe: Mock):
        """Test needed_inputs calculation when sub_pipe has batch_params"""

        # Set up the mock to return a pipe that normally needs "item"
        def mock_get_pipe_side_effect(pipe_code: str):
            if pipe_code == "batch_pipe":
                mock_pipe = Mock()
                mock_pipe.inputs = PipeInputSpec(root={"item": "test_domain.Item", "context": "test_domain.Context"})
                del mock_pipe.needed_inputs
                return mock_pipe
            else:
                raise Exception(f"Unknown pipe: {pipe_code}")

        mock_get_pipe.side_effect = mock_get_pipe_side_effect

        # Create batch_params mock
        batch_params_mock = Mock()
        batch_params_mock.input_item_stuff_name = "item"

        # Create PipeParallel with batching
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec(root={"context": "test_domain.Context"}),  # "item" not needed due to batching
            output_concept_code="test_domain.Result",
            parallel_sub_pipes=[
                SubPipe(pipe_code="batch_pipe", output_name="result", batch_params=batch_params_mock),
            ],
            add_each_output=True,
            combined_output=None,
        )

        # Test needed_inputs calculation
        needed_inputs = pipe_parallel.needed_inputs()

        # Should need: context (from pipe) but NOT item (excluded due to batching)
        assert "context" in needed_inputs.root
        assert "item" not in needed_inputs.root
        assert len(needed_inputs.root) == 1

    @patch("pipelex.pipe_controllers.pipe_parallel.get_required_pipe")
    def test_pipe_parallel_needed_inputs_with_nested_controllers(self, mock_get_pipe: Mock):
        """Test needed_inputs calculation with nested controller pipes (PipeCondition, PipeSequence, etc.)"""

        # Set up the mock to return a nested controller pipe
        def mock_get_pipe_side_effect(pipe_code: str):
            if pipe_code == "nested_condition":
                mock_pipe = Mock()
                mock_pipe.__class__.__name__ = "PipeCondition"

                # Mock the needed_inputs method for nested controller
                def mock_needed_inputs(_visited_pipes: Optional[Set[str]] = None):
                    return PipeInputSpec(root={"condition_var": "test_domain.Text", "option_var": "test_domain.Option"})

                mock_pipe.needed_inputs = mock_needed_inputs
                return mock_pipe
            else:
                raise Exception(f"Unknown pipe: {pipe_code}")

        mock_get_pipe.side_effect = mock_get_pipe_side_effect

        # Create PipeParallel with nested controller
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec(
                root={
                    "condition_var": "test_domain.Text",
                    "option_var": "test_domain.Option",
                }
            ),
            output_concept_code="test_domain.Result",
            parallel_sub_pipes=[
                SubPipe(pipe_code="nested_condition", output_name="result"),
            ],
            add_each_output=True,
            combined_output=None,
        )

        # Test needed_inputs calculation
        needed_inputs = pipe_parallel.needed_inputs()

        # Should need inputs from the nested controller
        assert "condition_var" in needed_inputs.root
        assert "option_var" in needed_inputs.root
        assert len(needed_inputs.root) == 2

    def test_pipe_parallel_recursion_prevention(self):
        """Test that needed_inputs prevents infinite recursion"""
        pipe_parallel = PipeParallel(
            domain="test_domain",
            code="test_parallel",
            inputs=PipeInputSpec(root={"input": "test_domain.Text"}),
            output_concept_code="test_domain.Result",
            parallel_sub_pipes=[],
            add_each_output=True,
            combined_output=None,
        )

        # Test with visited_pipes containing self
        visited_pipes = {"test_parallel"}
        needed_inputs = pipe_parallel.needed_inputs(_visited_pipes=visited_pipes)

        # Should return empty PipeInputSpec due to recursion prevention
        assert len(needed_inputs.root) == 0
