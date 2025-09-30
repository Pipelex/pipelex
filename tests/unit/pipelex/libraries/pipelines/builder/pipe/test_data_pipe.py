from typing import ClassVar

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint

from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec


class PipeBlueprintTestCases:
    SIMPLE_PIPE = (
        "simple_pipe",
        PipeSpec(
            type="PipeLLM",
            category="PipeOperator",
            definition="A simple pipe",
            inputs={"input": "Text"},
            output="ProcessedText",
        ),
        PipeBlueprint(
            type="PipeLLM",
            category="PipeOperator",
            definition="A simple pipe",
            inputs={"input": InputRequirementBlueprint(concept="Text")},
            output="ProcessedText",
        ),
    )

    PIPE_WITH_INPUT_REQUIREMENTS = (
        "pipe_with_requirements",
        PipeSpec(
            type="PipeFunc",
            category="PipeOperator",
            definition="Pipe with input requirements",
            inputs={
                "data": "Data",
                "config": "Config",
            },
            output="Result",
        ),
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
    )

    PIPE_NO_INPUTS = (
        "pipe_no_inputs",
        PipeSpec(
            type="PipeFunc",
            category="PipeOperator",
            definition="Pipe without inputs",
            inputs={},
            output="GeneratedData",
        ),
        PipeBlueprint(
            type="PipeFunc",
            category="PipeOperator",
            definition="Pipe without inputs",
            inputs=None,
            output="GeneratedData",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeSpec, PipeBlueprint]]] = [
        SIMPLE_PIPE,
        PIPE_WITH_INPUT_REQUIREMENTS,
        PIPE_NO_INPUTS,
    ]
