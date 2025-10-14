from typing import ClassVar

from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class PipeLLMTestCases:
    SIMPLE_LLM = (
        "simple_llm",
        PipeLLMSpec(
            pipe_code="test_pipe",
            description="Generate text",
            inputs={"topic": "Text"},
            output="Text",
            llm="llm_for_creative_writing",
            prompt="Write about $topic",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate text",
            inputs={"topic": InputRequirementBlueprint(concept="Text")},
            output="Text",
            prompt="Write about $topic",
            model="claude-4.1-opus",
        ),
    )

    LLM_NO_INPUTS = (
        "llm_no_inputs",
        PipeLLMSpec(
            pipe_code="generate_pipe",
            description="Generate without inputs",
            inputs={},
            output="Text",
            llm="llm_for_creative_writing",
            prompt="Generate something interesting",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate without inputs",
            output="Text",
            prompt="Generate something interesting",
            model="claude-4.1-opus",
        ),
    )

    LLM_WITH_VISION_INPUT = (
        "llm_with_vision_input",
        PipeLLMSpec(
            pipe_code="analyze_image",
            description="Analyze image",
            inputs={"image": "Image"},
            output="Text",
            prompt="Analyze the image: $image",
            llm="llm_cheap_for_vision",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Analyze image",
            inputs={"image": InputRequirementBlueprint(concept="Image")},
            output="Text",
            prompt="Analyze the image: $image",
            model="gemini-2.5-flash-lite",
        ),
    )

    LLM_WITH_PRESET = (
        "llm_with_preset",
        PipeLLMSpec(
            pipe_code="generate",
            description="Generate with preset",
            inputs={},
            output="Text",
            prompt="Generate text",
            llm="llm_to_reason",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate with preset",
            model="claude-4.5-sonnet",
            output="Text",
            prompt="Generate text",
        ),
    )

    LLM_WITH_SETTINGS = (
        "llm_with_settings",
        PipeLLMSpec(
            pipe_code="generate",
            description="Generate with settings",
            inputs={},
            output="Text",
            prompt="Generate text",
            llm="llm_cheap_for_easy_questions",
            temperature=0.7,
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate with settings",
            model=LLMSetting(
                model="claude-4.5-sonnet",
                temperature=0.7,
                max_tokens=None,  # "auto" is handled at conversion to core
            ),
            output="Text",
            prompt="Generate text",
        ),
    )

    LLM_WITH_SYSTEM_PROMPT = (
        "llm_with_system_prompt",
        PipeLLMSpec(
            pipe_code="analyze",
            description="Generate with system prompt",
            inputs={"data": "Data"},
            output="Analysis",
            system_prompt="You are a data analyst",
            prompt="Analyze: @data",
            llm="llm_to_analyze_data",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate with system prompt",
            inputs={"data": InputRequirementBlueprint(concept="Data")},
            system_prompt="You are a data analyst",
            prompt="Analyze: @data",
            output="Analysis",
            model="claude-4.5-sonnet",
        ),
    )

    LLM_WITH_MULTIPLE_OUTPUT = (
        "llm_with_multiple_output",
        PipeLLMSpec(
            pipe_code="generate_items",
            description="Generate multiple items",
            inputs={},
            output="Item",
            prompt="Generate items",
            multiple_output=True,
            llm="llm_cheap_for_easy_questions",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate multiple items",
            multiple_output=True,
            nb_output=None,
            output="Item",
            prompt="Generate items",
            model="claude-4.5-sonnet",
        ),
    )

    LLM_WITH_FIXED_OUTPUT = (
        "llm_with_fixed_output",
        PipeLLMSpec(
            pipe_code="generate_items",
            description="Generate exactly 5 items",
            inputs={},
            output="Item",
            prompt="Generate items",
            nb_output=5,
            llm="llm_cheap_for_easy_questions",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate exactly 5 items",
            nb_output=5,
            multiple_output=None,
            output="Item",
            prompt="Generate items",
            model="claude-4.5-sonnet",
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeLLMSpec, PipeLLMBlueprint]]] = [
        SIMPLE_LLM,
        LLM_NO_INPUTS,
        LLM_WITH_VISION_INPUT,
        LLM_WITH_PRESET,
        LLM_WITH_SETTINGS,
        LLM_WITH_SYSTEM_PROMPT,
        LLM_WITH_MULTIPLE_OUTPUT,
        LLM_WITH_FIXED_OUTPUT,
    ]
