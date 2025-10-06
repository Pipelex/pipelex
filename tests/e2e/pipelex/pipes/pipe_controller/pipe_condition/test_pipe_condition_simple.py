"""Test simple pipe condition functionality with dry run validation."""

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.input_requirements import TypedNamedInputRequirement
from pipelex.exceptions import DryRunError
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_factory import PipeConditionFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.test_pipelines.pipe_controllers.pipe_condition.pipe_condition import CategoryInput


@pytest.mark.dry_runnable
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeConditionSimple:
    async def test_direct_pipe_condition_should_fail(self):
        """Test a PipeCondition created directly in code that should FAIL dry run."""
        # Create a PipeCondition directly in Python that requires an input
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Test condition that should fail",
            inputs={"user_category": InputRequirementBlueprint(concept="test_pipe_condition.CategoryInput")},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
            expression_template="{{ user_category.category }}",
            outcomes={"small": "process_small", "medium": "process_medium", "large": "process_large"},
            default_outcome="process_small",
        )

        pipe_condition = PipeConditionFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="test_condition_fail",
            blueprint=pipe_condition_blueprint,
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
        pipe_condition_blueprint = PipeConditionBlueprint(
            description="Test condition that should succeed",
            inputs={"user_status": InputRequirementBlueprint(concept="test_pipe_condition.CategoryInput")},
            output=f"{SpecialDomain.NATIVE}.{NativeConceptCode.TEXT}",
            expression_template="{{ user_status.category }}",
            outcomes={"active": "process_small", "inactive": "process_medium", "pending": "process_large"},
            default_outcome="process_small",
        )

        pipe_condition = PipeConditionFactory.make_from_blueprint(
            domain="test_domain",
            pipe_code="test_condition_succeed",
            blueprint=pipe_condition_blueprint,
        )

        # Test with proper working memory - should SUCCEED or fail at expression evaluation (not missing inputs)
        working_memory = WorkingMemoryFactory.make_for_dry_run(
            needed_inputs=[
                TypedNamedInputRequirement(
                    variable_name="user_status",
                    concept=ConceptFactory.make(
                        concept_code="CategoryInput",
                        domain="test_pipe_condition",
                        description="CategoryInput",
                        structure_class_name="CategoryInput",
                    ),
                    structure_class=CategoryInput,
                ),
            ],
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
            msg_exc = str(exc)
            # If it fails, it should NOT be due to missing inputs
            assert "missing required inputs" not in str(msg_exc)
            # Should be due to expression evaluation or other validation
            assert any(keyword in str(msg_exc) for keyword in ["expression", "evaluation", "empty result"])
            print(f"✅ Direct PipeCondition passed input validation, failed at expression evaluation (expected): {exc}")
        print("✅ Direct PipeCondition test completed successfully!")
