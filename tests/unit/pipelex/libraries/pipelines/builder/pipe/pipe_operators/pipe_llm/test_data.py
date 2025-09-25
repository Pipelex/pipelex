from typing import ClassVar

from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_llm_spec import LLMSettingSpec, PipeLLMSpec
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint, StructuringMethod


class PipeLLMTestCases:
    SIMPLE_LLM = (
        "simple_llm",
        PipeLLMSpec(
            the_pipe_code="test_pipe",
            definition="Generate text",
            inputs={"topic": InputRequirementSpec(concept="Text")},
            output="Text",
            prompt_template="Write about $topic",
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate text",
            inputs={"topic": InputRequirementBlueprint(concept="Text")},
            output="Text",
            prompt_template="Write about $topic",
        ),
    )

    LLM_NO_INPUTS = (
        "llm_no_inputs",
        PipeLLMSpec(
            the_pipe_code="generate_pipe",
            definition="Generate without inputs",
            inputs=None,
            output="Text",
            prompt_template="Generate something interesting",
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate without inputs",
            output="Text",
            prompt_template="Generate something interesting",
        ),
    )

    LLM_WITH_PRESET = (
        "llm_with_preset",
        PipeLLMSpec(
            the_pipe_code="generate",
            definition="Generate with preset",
            inputs=None,
            output="Text",
            prompt_template="Generate text",
            llm="llm_to_reason",
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate with preset",
            llm="llm_to_reason",
            output="Text",
            prompt_template="Generate text",
        ),
    )

    LLM_WITH_SETTINGS = (
        "llm_with_settings",
        PipeLLMSpec(
            the_pipe_code="generate",
            definition="Generate with settings",
            inputs=None,
            output="Text",
            prompt_template="Generate text",
            llm=LLMSettingSpec(
                llm_handle="gpt-4o-mini",
                temperature=0.7,
                max_tokens=None,  # "auto" is handled at conversion to core
            ),
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate with settings",
            llm=LLMSetting(
                llm_handle="gpt-4o-mini",
                temperature=0.7,
                max_tokens=None,  # "auto" is handled at conversion to core
            ),
            output="Text",
            prompt_template="Generate text",
        ),
    )

    LLM_WITH_SYSTEM_PROMPT = (
        "llm_with_system_prompt",
        PipeLLMSpec(
            the_pipe_code="analyze",
            definition="Generate with system prompt",
            inputs={"data": InputRequirementSpec(concept="Data")},
            output="Analysis",
            system_prompt="You are a data analyst",
            prompt_template="Analyze: @data",
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate with system prompt",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            system_prompt="You are a data analyst",
            prompt_template="Analyze: @data",
            output="Analysis",
        ),
    )

    LLM_WITH_MULTIPLE_OUTPUT = (
        "llm_with_multiple_output",
        PipeLLMSpec(
            the_pipe_code="generate_items",
            definition="Generate multiple items",
            inputs=None,
            output="Item",
            prompt_template="Generate items",
            multiple_output=True,
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate multiple items",
            multiple_output=True,
            nb_output=None,
            output="Item",
            prompt_template="Generate items",
        ),
    )

    LLM_WITH_FIXED_OUTPUT = (
        "llm_with_fixed_output",
        PipeLLMSpec(
            the_pipe_code="generate_items",
            definition="Generate exactly 5 items",
            inputs=None,
            output="Item",
            prompt_template="Generate items",
            nb_output=5,
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Generate exactly 5 items",
            nb_output=5,
            multiple_output=None,
            output="Item",
            prompt_template="Generate items",
        ),
    )

    LLM_WITH_STRUCTURING = (
        "llm_with_structuring",
        PipeLLMSpec(
            the_pipe_code="test_pipe",
            definition="Extract structured data",
            inputs=None,
            output="PersonInfo",
            prompt_template="Extract person info",
            llm="llm_to_extract",
            llm_to_structure=LLMSettingSpec(
                llm_handle="claude-3-sonnet",
                temperature=0.1,
                max_tokens=None,  # "auto" is handled at conversion to core
            ),
            structuring_method=StructuringMethod.PRELIMINARY_TEXT,
            prompt_template_to_structure="Structure the output",
            system_prompt_to_structure="You are a data structurer",
        ),
        PipeLLMBlueprint(
            type="PipeLLM",
            definition="Extract structured data",
            structuring_method=StructuringMethod.PRELIMINARY_TEXT,
            prompt_template_to_structure="Structure the output",
            system_prompt_to_structure="You are a data structurer",
            llm="llm_to_extract",
            llm_to_structure=LLMSetting(
                llm_handle="claude-3-sonnet",
                temperature=0.1,
                max_tokens=None,  # "auto" is handled at conversion to core
            ),
            output="PersonInfo",
            prompt_template="Extract person info",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeLLMSpec, PipeLLMBlueprint]]] = [
        SIMPLE_LLM,
        LLM_NO_INPUTS,
        LLM_WITH_PRESET,
        LLM_WITH_SETTINGS,
        LLM_WITH_SYSTEM_PROMPT,
        LLM_WITH_MULTIPLE_OUTPUT,
        LLM_WITH_FIXED_OUTPUT,
        LLM_WITH_STRUCTURING,
    ]
