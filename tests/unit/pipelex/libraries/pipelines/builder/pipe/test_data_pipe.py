"""
Test data for base PipeBlueprint conversion tests.
"""

from typing import ClassVar, List, Tuple

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint as PipeBlueprintCore
from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeBlueprint


class PipeBlueprintTestCases:
    """Test cases for base PipeBlueprint conversion."""

    SIMPLE_PIPE = (
        "simple_pipe",
        PipeBlueprint(
            type="PipeLLM",
            category="PipeOperator",
            definition="A simple pipe",
            inputs={"input": "Text"},
            output="ProcessedText",
        ),
        "simple_pipe",
        "test_domain",
        PipeBlueprintCore(
            type="PipeLLM",
            category="PipeOperator",
            definition="A simple pipe",
            inputs={"input": InputRequirementBlueprintCore(concept="Text")},
            output="ProcessedText",
        ),
    )

    PIPE_WITH_INPUT_REQUIREMENTS = (
        "pipe_with_requirements",
        PipeBlueprint(
            type="PipeFunc",
            category="PipeOperator",
            definition="Pipe with input requirements",
            inputs={
                "data": InputRequirementBlueprint(concept="Data"),
                "config": InputRequirementBlueprint(concept="Config"),
            },
            output="Result",
        ),
        "requirement_pipe",
        "test_domain",
        PipeBlueprintCore(
            type="PipeFunc",
            category="PipeOperator",
            definition="Pipe with input requirements",
            inputs={
                "data": InputRequirementBlueprintCore(concept="Data"),
                "config": InputRequirementBlueprintCore(concept="Config"),
            },
            output="Result",
        ),
    )

    PIPE_NO_INPUTS = (
        "pipe_no_inputs",
        PipeBlueprint(
            type="PipeFunc",
            category="PipeOperator",
            definition="Pipe without inputs",
            inputs={},
            output="GeneratedData",
        ),
        "generator_pipe",
        "test_domain",
        PipeBlueprintCore(
            type="PipeFunc",
            category="PipeOperator",
            definition="Pipe without inputs",
            inputs=None,
            output="GeneratedData",
        ),
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeBlueprint, str, str, PipeBlueprintCore]]] = [
        SIMPLE_PIPE,
        PIPE_WITH_INPUT_REQUIREMENTS,
        PIPE_NO_INPUTS,
    ]
