"""Test simple pipe condition functionality with dry run validation."""

import pytest

from pipelex import pretty_print
from pipelex.core.pipe_input_spec import PipeInputSpec, TypedNamedInputRequirement
from pipelex.core.pipe_run_params import PipeRunMode
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.exceptions import DryRunError
from pipelex.pipe_controllers.pipe_condition import PipeCondition
from pipelex.pipeline.job_metadata import JobMetadata
from tests.test_pipelines.pipe_controllers.pipe_condition.pipe_condition import CategoryInput


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionSimple:
    async def test_direct_pipe_condition_should_fail(self):
        """Test a PipeCondition created directly in code that should FAIL dry run."""
        # Create a PipeCondition directly in Python that requires an input
        pipe_condition = PipeCondition(
            code="test_condition_fail",
            domain="test_domain",
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"user_category": "test_pipe_condition.CategoryInput"}),
            output_concept_code="native.Text",
            expression_template="{{ user_category.category }}",
            pipe_map={"small": "process_small", "medium": "process_medium", "large": "process_large"},
            default_pipe_code="process_small",
        )

        # Test with empty working memory - should FAIL
        empty_working_memory = WorkingMemoryFactory.make_empty()

        with pytest.raises(DryRunError) as exc_info:
            await pipe_condition.run_pipe(
                job_metadata=JobMetadata(job_name="test_direct_condition_fail"),
                working_memory=empty_working_memory,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            )

        # Verify it failed for the right reason
        error = exc_info.value
        assert error.pipe_code == "test_condition_fail"
        assert "user_category" in error.missing_inputs
        assert "missing required inputs" in str(error)

    async def test_direct_pipe_condition_should_succeed(self):
        """Test a PipeCondition created directly in code that should SUCCEED dry run."""
        # Create a PipeCondition directly in Python
        pipe_condition = PipeCondition(
            code="test_condition_succeed",
            domain="test_domain",
            inputs=PipeInputSpec.make_from_dict(concepts_dict={"user_status": "test_pipe_condition.CategoryInput"}),
            output_concept_code="native.Text",
            expression_template="{{ user_status.category }}",
            pipe_map={
                "active": "process_small",  # Map to existing pipes
                "inactive": "process_medium",
                "pending": "process_large",
            },
            default_pipe_code="process_small",
        )

        # Test with proper working memory - should SUCCEED or fail at expression evaluation (not missing inputs)
        working_memory = WorkingMemoryFactory.make_for_dry_run(
            needed_inputs=[
                TypedNamedInputRequirement(
                    variable_name="user_status",
                    concept_code="test_pipe_condition.CategoryInput",
                    structure_class=CategoryInput,
                )
            ]
        )

        try:
            pipe_output = await pipe_condition.run_pipe(
                job_metadata=JobMetadata(job_name="test_direct_condition_succeed"),
                working_memory=working_memory,
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            )

            # If it succeeds completely
            assert pipe_output is not None
            assert pipe_output.working_memory is not None
            print("✅ Direct PipeCondition SUCCEEDED completely!")
            pretty_print(pipe_output)

        except DryRunError as exc:
            # If it fails, it should NOT be due to missing inputs
            assert "missing required inputs" not in str(exc)
            # Should be due to expression evaluation or other validation
            assert any(keyword in str(exc) for keyword in ["expression", "evaluation", "empty result"])
            print(f"✅ Direct PipeCondition passed input validation, failed at expression evaluation (expected): {exc}")

        print("✅ Direct PipeCondition test completed successfully!")
