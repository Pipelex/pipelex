from typing import ClassVar

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeBlueprintTestCases:
    SIMPLE_PIPE = (
        "simple_pipe",
        PipeSpec(
            pipe_code="simple_pipe",
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="A simple pipe",
            inputs={"input": "Text"},
            output="ProcessedText",
        ),
        PipeBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="A simple pipe",
            inputs={"input": InputRequirementBlueprint(concept="Text")},
            output="ProcessedText",
        ),
    )

    PIPE_WITH_INPUT_REQUIREMENTS = (
        "pipe_with_requirements",
        PipeSpec(
            pipe_code="pipe_with_requirements",
            type="PipeFunc",
            pipe_category="PipeOperator",
            description="Pipe with input requirements",
            inputs={
                "data": "Data",
                "config": "Config",
            },
            output="Result",
        ),
        PipeBlueprint(
            type="PipeFunc",
            pipe_category="PipeOperator",
            description="Pipe with input requirements",
            inputs={
                "data": InputRequirementBlueprint(concept="Data"),
                "config": InputRequirementBlueprint(concept="Config"),
            },
            output="Result",
        ),
    )

    PIPE_NO_INPUTS = (
        "pipe_no_inputs",
        PipeSpec(
            pipe_code="pipe_no_inputs",
            type="PipeFunc",
            pipe_category="PipeOperator",
            description="Pipe without inputs",
            inputs={},
            output="GeneratedData",
        ),
        PipeBlueprint(
            type="PipeFunc",
            pipe_category="PipeOperator",
            description="Pipe without inputs",
            inputs=None,
            output="GeneratedData",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeSpec, PipeBlueprint]]] = [
        SIMPLE_PIPE,
        PIPE_WITH_INPUT_REQUIREMENTS,
        PIPE_NO_INPUTS,
    ]
