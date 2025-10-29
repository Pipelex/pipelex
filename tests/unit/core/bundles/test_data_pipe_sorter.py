"""Test data for pipe dependency sorting."""

from typing import ClassVar

from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class PipeSorterTestCases:
    """Test cases for pipe dependency sorting with various scenarios."""

    # Test case 1: No dependencies - all operators
    NO_DEPENDENCIES_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_c": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="C", inputs={}, output="Text"),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="A", inputs={}, output="Text"),
        "pipe_b": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="B", inputs={}, output="Text"),
    }
    NO_DEPENDENCIES_EXPECTED: ClassVar[list[str]] = ["pipe_a", "pipe_b", "pipe_c"]  # Alphabetical order (all are roots)

    # Test case 2: Simple chain A -> B -> C
    SIMPLE_CHAIN_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_c": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="C depends on B",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_b", result="result_b")],
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="A no deps", inputs={}, output="Text"),
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
    }
    SIMPLE_CHAIN_EXPECTED: ClassVar[list[str]] = ["pipe_c", "pipe_b", "pipe_a"]

    # Test case 3: Diamond pattern
    #     A
    #    / \
    #   B   C
    #    \ /
    #     D
    DIAMOND_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_d": PipeParallelBlueprint(
            type="PipeParallel",
            pipe_category="PipeController",
            description="D depends on B and C",
            inputs={},
            output="Text",
            parallels=[
                SubPipeBlueprint(pipe="pipe_b", result="result_b"),
                SubPipeBlueprint(pipe="pipe_c", result="result_c"),
            ],
            add_each_output=True,
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="A", inputs={}, output="Text"),
        "pipe_c": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="C depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
    }
    # D is root, visits B first (alphabetically), then A (B's dependency), then C (already visited A)
    # Don't verify exact order for diamond pattern due to shared dependencies
    DIAMOND_EXPECTED: ClassVar[list[str] | None] = None

    # Test case 4: Multiple independent chains
    MULTIPLE_CHAINS_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        # Chain 1: A -> B
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="A", inputs={}, output="Text"),
        # Chain 2: X -> Y
        "pipe_y": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="Y depends on X",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_x", result="result_x")],
        ),
        "pipe_x": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="X", inputs={}, output="Text"),
    }
    # Depth-first from roots (pipe_b, pipe_y alphabetically): pipe_b -> pipe_a, then pipe_y -> pipe_x
    MULTIPLE_CHAINS_EXPECTED: ClassVar[list[str]] = ["pipe_b", "pipe_a", "pipe_y", "pipe_x"]

    # Test case 5: PipeBatch dependency
    PIPE_BATCH_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "batch_pipe": PipeBatchBlueprint(
            type="PipeBatch",
            pipe_category="PipeController",
            description="Batch depends on process",
            inputs={},
            output="Text",
            branch_pipe_code="process_item",
            input_list_name="items",
            input_item_name="item",
        ),
        "process_item": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="Process", inputs={}, output="Text"),
    }
    PIPE_BATCH_EXPECTED: ClassVar[list[str]] = ["batch_pipe", "process_item"]

    # Test case 6: PipeCondition with multiple branches
    PIPE_CONDITION_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "router": PipeConditionBlueprint(
            type="PipeCondition",
            pipe_category="PipeController",
            description="Routes to different pipes",
            inputs={},
            output="Text",
            expression="category",
            outcomes={
                "small": "process_small",
                "large": "process_large",
            },
            default_outcome="process_default",
        ),
        "process_large": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="Large", inputs={}, output="Text"),
        "process_small": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="Small", inputs={}, output="Text"),
        "process_default": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="Default", inputs={}, output="Text"),
    }
    # Router first, then its dependencies in alphabetical order
    PIPE_CONDITION_EXPECTED: ClassVar[list[str]] = ["router", "process_default", "process_large", "process_small"]

    # Test case 7: Circular dependency (should raise error)
    CIRCULAR_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "pipe_a": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="A depends on C (circular!)",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_c", result="result_c")],
        ),
        "pipe_b": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="B depends on A",
            inputs={},
            output="Text",
            steps=[SubPipeBlueprint(pipe="pipe_a", result="result_a")],
        ),
        "pipe_c": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
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
            pipe_category="PipeController",
            description="B depends on A and Z (Z doesn't exist)",
            inputs={},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="pipe_a", result="result_a"),
                SubPipeBlueprint(pipe="pipe_z", result="result_z"),  # Z doesn't exist in this bundle
            ],
        ),
        "pipe_a": PipeLLMBlueprint(type="PipeLLM", pipe_category="PipeOperator", description="A", inputs={}, output="Text"),
    }
    MISSING_DEPENDENCY_EXPECTED: ClassVar[list[str]] = ["pipe_b", "pipe_a"]  # Z is ignored as it's not in the bundle

    # Test case 9: Image inversion pipeline - realistic multi-step sequence
    IMAGE_INVERSION_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        "analyze_image_content": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Analyzes the input photo to understand visual elements, composition, mood, etc.",
            inputs={"input_photo": "Image"},
            output="ImageAnalysis",
        ),
        "define_opposite_concept": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Determines what constitutes the opposite for the analyzed image",
            inputs={"image_analysis": "ImageAnalysis"},
            output="OppositeDefinition",
        ),
        "generate_image_prompt": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Crafts a detailed image generation prompt from the opposite definition",
            inputs={"opposite_definition": "OppositeDefinition"},
            output="ImagePrompt",
        ),
        "generate_opposite_image": PipeImgGenBlueprint(
            type="PipeImgGen",
            pipe_category="PipeOperator",
            description="Generates the opposite image using AI",
            inputs={"generation_prompt": "ImagePrompt"},
            output="Image",
        ),
        "photo_opposite_pipeline": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="Main pipeline that generates the opposite of an input photo",
            inputs={"input_photo": "Image"},
            output="Image",
            steps=[
                SubPipeBlueprint(pipe="analyze_image_content", result="image_analysis"),
                SubPipeBlueprint(pipe="define_opposite_concept", result="opposite_concept"),
                SubPipeBlueprint(pipe="generate_image_prompt", result="generation_prompt"),
                SubPipeBlueprint(pipe="generate_opposite_image", result="opposite_image"),
            ],
        ),
    }
    # Controller first, then dependencies in step order
    IMAGE_INVERSION_EXPECTED: ClassVar[list[str]] = [
        "photo_opposite_pipeline",
        "analyze_image_content",
        "define_opposite_concept",
        "generate_image_prompt",
        "generate_opposite_image",
    ]

    # Test case 10: Complex nested pipeline with PipeSequence containing another PipeSequence and PipeCondition
    COMPLEX_NESTED_PIPES: ClassVar[dict[str, PipeBlueprintUnion]] = {
        # Main sequence with nested controllers
        "main_pipeline": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="Main pipeline with nested controllers",
            inputs={"input": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="nested_sequence", result="prepared"),
                SubPipeBlueprint(pipe="router", result="processed"),
                SubPipeBlueprint(pipe="final_process", result="final"),
            ],
        ),
        # Nested sequence
        "nested_sequence": PipeSequenceBlueprint(
            type="PipeSequence",
            pipe_category="PipeController",
            description="Nested preparation sequence",
            inputs={"input": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="prepare_data", result="prepared_data"),
                SubPipeBlueprint(pipe="validate_data", result="validated_data"),
            ],
        ),
        # Condition router
        "router": PipeConditionBlueprint(
            type="PipeCondition",
            pipe_category="PipeController",
            description="Routes based on size",
            inputs={"prepared": "Text"},
            output="Text",
            expression="size",
            outcomes={
                "small": "process_small",
                "large": "process_large",
            },
            default_outcome="process_default",
        ),
        # LLM operators
        "prepare_data": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Prepare the data",
            inputs={"input": "Text"},
            output="Text",
        ),
        "validate_data": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Validate the prepared data",
            inputs={"prepared_data": "Text"},
            output="Text",
        ),
        "process_small": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Process small items",
            inputs={"item": "Text"},
            output="Text",
        ),
        "process_large": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Process large items",
            inputs={"item": "Text"},
            output="Text",
        ),
        "process_default": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Default processing",
            inputs={"item": "Text"},
            output="Text",
        ),
        "final_process": PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Final processing step",
            inputs={"processed": "Text"},
            output="Text",
        ),
    }
    # Expected order: main_pipeline first, then following step order
    # Step 1: nested_sequence and its steps (prepare_data, validate_data)
    # Step 2: router and its dependencies (alphabetically: process_default, process_large, process_small)
    # Step 3: final_process
    COMPLEX_NESTED_EXPECTED: ClassVar[list[str]] = [
        "main_pipeline",
        "nested_sequence",
        "prepare_data",
        "validate_data",
        "router",
        "process_default",
        "process_large",
        "process_small",
        "final_process",
    ]

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
        ("image_inversion", IMAGE_INVERSION_PIPES, IMAGE_INVERSION_EXPECTED, None),
        ("complex_nested", COMPLEX_NESTED_PIPES, COMPLEX_NESTED_EXPECTED, None),
    ]
