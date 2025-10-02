"""Test data for pipe dependency sorting."""

from typing import ClassVar

from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class PipeSorterTestCases:
    """Test cases for pipe dependency sorting with various scenarios."""

    # Test case 1: No dependencies - all operators
    NO_DEPENDENCIES_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_c": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="C", inputs={}, output="Text"),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="A", inputs={}, output="Text"),
        "pipe_b": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="B", inputs={}, output="Text"),
    }
    NO_DEPENDENCIES_EXPECTED: ClassVar[list[str]] = ["pipe_a", "pipe_b", "pipe_c"]  # Alphabetical order

    # Test case 2: Simple chain A -> B -> C
    SIMPLE_CHAIN_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_c": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="C depends on B",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_b", result="result_b")],
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="A no deps", inputs={}, output="Text"),
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
    }
    SIMPLE_CHAIN_EXPECTED: ClassVar[list[str]] = ["pipe_a", "pipe_b", "pipe_c"]

    # Test case 3: Diamond pattern
    #     A
    #    / \
    #   B   C
    #    \ /
    #     D
    DIAMOND_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_d": PipeParallelBlueprint(
            type="PipeParallel",
            category="PipeController",
            description="D depends on B and C",
            inputs={},
            output="Text",
            parallels=[
                SubPipeBlueprint(pipe="pipe_b", result="result_b"),
                SubPipeBlueprint(pipe="pipe_c", result="result_c"),
            ],
            add_each_output=True,
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="A", inputs={}, output="Text"),
        "pipe_c": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="C depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
    }
    # A must come first, then B and C (in any order), then D
    DIAMOND_EXPECTED: ClassVar[list[str]] = ["pipe_a", "pipe_b", "pipe_c", "pipe_d"]

    # Test case 4: Multiple independent chains
    MULTIPLE_CHAINS_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        # Chain 1: A -> B
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="A", inputs={}, output="Text"),
        # Chain 2: X -> Y
        "pipe_y": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="Y depends on X",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_x", result="result_x")],
        ),
        "pipe_x": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="X", inputs={}, output="Text"),
    }
    # Within each level, pipes are sorted alphabetically
    # Level 1: pipe_a, pipe_x (both have no deps, sorted alphabetically)
    # Level 2: pipe_b (depends on pipe_a), pipe_y (depends on pipe_x)
    # Since pipe_b depends on pipe_a which comes first, pipe_b is processed before pipe_y
    MULTIPLE_CHAINS_EXPECTED: ClassVar[list[str]] = ["pipe_a", "pipe_b", "pipe_x", "pipe_y"]

    # Test case 5: PipeBatch dependency
    PIPE_BATCH_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "batch_pipe": PipeBatchBlueprint(
            type="PipeBatch",
            category="PipeController",
            description="Batch depends on process",
            inputs={},
            output="Text",
            branch_pipe_code="process_item",
        ),
        "process_item": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="Process", inputs={}, output="Text"),
    }
    PIPE_BATCH_EXPECTED: ClassVar[list[str]] = ["process_item", "batch_pipe"]

    # Test case 6: PipeCondition with multiple branches
    PIPE_CONDITION_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "router": PipeConditionBlueprint(
            type="PipeCondition",
            category="PipeController",
            description="Routes to different pipes",
            inputs={},
            output="Text",
            expression="category",
            pipe_map={
                "small": "process_small",
                "large": "process_large",
            },
            default_pipe_code="process_default",
        ),
        "process_large": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="Large", inputs={}, output="Text"),
        "process_small": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="Small", inputs={}, output="Text"),
        "process_default": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="Default", inputs={}, output="Text"),
    }
    # All process pipes must come before router
    PIPE_CONDITION_EXPECTED: ClassVar[list[str]] = ["process_default", "process_large", "process_small", "router"]

    # Test case 7: Circular dependency (should raise error)
    CIRCULAR_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_a": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="A depends on C (circular!)",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_c", result="result_c")],
        ),
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
        "pipe_c": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="C depends on B",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_b", result="result_b")],
        ),
    }

    # Test case 8: Reference to non-existent pipe (should be ignored in sorting)
    MISSING_DEPENDENCY_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            category="PipeController",
            description="B depends on A and Z (Z doesn't exist)",
            inputs={},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="pipe_a", result="result_a"),
                SubPipeBlueprint(pipe="pipe_z", result="result_z"),  # Z doesn't exist in this bundle
            ],
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", category="PipeOperator", description="A", inputs={}, output="Text"),
    }
    MISSING_DEPENDENCY_EXPECTED: ClassVar[list[str]] = ["pipe_a", "pipe_b"]  # Z is ignored as it's not in the bundle

    # Aggregate all test cases
    TEST_CASES: ClassVar[
        list[
            tuple[
                str,  # test_name
                dict[str, PipeBlueprintUnion],  # pipes
                list[str] | None,  # expected_order (None if should raise error)
                type[Exception] | None,  # expected_exception (None if should succeed)
            ]
        ]
    ] = [
        ("no_dependencies", NO_DEPENDENCIES_PIPES, NO_DEPENDENCIES_EXPECTED, None),
        ("simple_chain", SIMPLE_CHAIN_PIPES, SIMPLE_CHAIN_EXPECTED, None),
        ("diamond_pattern", DIAMOND_PIPES, DIAMOND_EXPECTED, None),
        ("multiple_chains", MULTIPLE_CHAINS_PIPES, MULTIPLE_CHAINS_EXPECTED, None),
        ("pipe_batch", PIPE_BATCH_PIPES, PIPE_BATCH_EXPECTED, None),
        ("pipe_condition", PIPE_CONDITION_PIPES, PIPE_CONDITION_EXPECTED, None),
        ("circular_dependency", CIRCULAR_PIPES, None, PipeDefinitionError),
        ("missing_dependency", MISSING_DEPENDENCY_PIPES, MISSING_DEPENDENCY_EXPECTED, None),
    ]
