import pytest
from pydantic import ValidationError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestPipelexBundleBlueprintPipeValidation:
    """Test validation of pipe references in PipelexBundleBlueprint."""

    # ========== VALID CASES ==========

    def test_valid_bare_step_refs_to_local_pipes(self):
        """Bare step refs (no domain prefix) should pass without validation at bundle level."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={"Result": "A result concept"},
            pipe={
                "step1": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Step 1",
                    output="Text",
                    prompt="Hello",
                ),
                "step2": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Step 2",
                    output="Result",
                    prompt="Process",
                ),
                "my_sequence": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Main sequence",
                    output="Result",
                    steps=[
                        SubPipeBlueprint(pipe="step1", result="intermediate"),
                        SubPipeBlueprint(pipe="step2", result="final"),
                    ],
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_external_pipe_ref_in_sequence(self):
        """External domain-qualified pipe ref should be skipped (not validated locally)."""
        bundle = PipelexBundleBlueprint(
            domain="orchestration",
            description="Test bundle",
            pipe={
                "my_sequence": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Orchestration sequence",
                    output="Text",
                    steps=[
                        SubPipeBlueprint(pipe="scoring.compute_score", result="score"),
                    ],
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_special_outcomes_not_treated_as_pipe_refs(self):
        """Special outcomes like 'fail' and 'continue' should not be validated as pipe refs."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={"Result": "A result concept"},
            pipe={
                "good_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Good pipe",
                    output="Result",
                    prompt="Do something",
                ),
                "my_condition": PipeConditionBlueprint(
                    type="PipeCondition",
                    description="Condition check",
                    output="Result",
                    expression="True",
                    outcomes={"True": "good_pipe"},
                    default_outcome="fail",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_external_batch_pipe_ref(self):
        """External domain-qualified branch_pipe_code should be skipped."""
        bundle = PipelexBundleBlueprint(
            domain="orchestration",
            description="Test bundle",
            pipe={
                "my_batch": PipeBatchBlueprint(
                    type="PipeBatch",
                    description="Batch process",
                    output="Text[]",
                    inputs={"items": "Text[]"},
                    branch_pipe_code="scoring.process_item",
                    input_list_name="items",
                    input_item_name="item",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_bare_ref_to_nonexistent_pipe(self):
        """Bare refs to pipes not declared locally should pass (deferred to package-level)."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            pipe={
                "my_sequence": PipeSequenceBlueprint(
                    type="PipeSequence",
                    description="Main sequence",
                    output="Text",
                    steps=[
                        SubPipeBlueprint(pipe="nonexistent_step", result="something"),
                    ],
                ),
            },
        )
        assert bundle.pipe is not None

    # ========== INVALID CASES ==========

    def test_invalid_same_domain_pipe_ref_to_nonexistent_pipe(self):
        """Same-domain qualified pipe ref to a non-existent pipe should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="my_domain",
                description="Test bundle",
                pipe={
                    "my_sequence": PipeSequenceBlueprint(
                        type="PipeSequence",
                        description="Main sequence",
                        output="Text",
                        steps=[
                            SubPipeBlueprint(pipe="my_domain.nonexistent_pipe", result="something"),
                        ],
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "my_domain.nonexistent_pipe" in error_message
        assert "not declared in domain" in error_message

    def test_invalid_same_domain_batch_pipe_ref(self):
        """Same-domain qualified branch_pipe_code to non-existent pipe should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="my_domain",
                description="Test bundle",
                pipe={
                    "my_batch": PipeBatchBlueprint(
                        type="PipeBatch",
                        description="Batch process",
                        output="Text[]",
                        inputs={"items": "Text[]"},
                        branch_pipe_code="my_domain.nonexistent_branch",
                        input_list_name="items",
                        input_item_name="item",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "my_domain.nonexistent_branch" in error_message

    def test_invalid_same_domain_condition_outcome_ref(self):
        """Same-domain qualified outcome pipe ref to non-existent pipe should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="my_domain",
                description="Test bundle",
                pipe={
                    "my_condition": PipeConditionBlueprint(
                        type="PipeCondition",
                        description="Condition check",
                        output="Text",
                        expression="True",
                        outcomes={"True": "my_domain.nonexistent_handler"},
                        default_outcome="fail",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "my_domain.nonexistent_handler" in error_message
