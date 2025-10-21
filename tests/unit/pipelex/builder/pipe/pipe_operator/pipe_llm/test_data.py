from typing import ClassVar

from pipelex.builder.pipe.pipe_llm_spec import LLMSkill, PipeLLMSpec
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class PipeLLMTestCases:
    SIMPLE_LLM = (
        "simple_llm",
        PipeLLMSpec(
            pipe_code="test_pipe",
            description="Generate text",
            inputs={"topic": "Text"},
            output="Text",
            llm_skill=LLMSkill.LLM_FOR_CREATIVE_WRITING,
            prompt="Write about $topic",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate text",
            inputs={"topic": "Text"},
            output="Text",
            prompt="Write about $topic",
            model=LLMSkill.LLM_FOR_CREATIVE_WRITING,
        ),
    )

    LLM_NO_INPUTS = (
        "llm_no_inputs",
        PipeLLMSpec(
            pipe_code="generate_pipe",
            description="Generate without inputs",
            inputs={},
            output="Text",
            llm_skill=LLMSkill.LLM_FOR_CREATIVE_WRITING,
            prompt="Generate something interesting",
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate without inputs",
            output="Text",
            prompt="Generate something interesting",
            model=LLMSkill.LLM_FOR_CREATIVE_WRITING,
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
            llm_skill=LLMSkill.LLM_FOR_BASIC_VISION,
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Analyze image",
            inputs={"image": "Image"},
            output="Text",
            prompt="Analyze the image: $image",
            model=LLMSkill.LLM_FOR_BASIC_VISION,
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
            llm_skill=LLMSkill.LLM_FOR_COMPLEX_REASONING,
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate with preset",
            model=LLMSkill.LLM_FOR_COMPLEX_REASONING,
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
            llm_skill=LLMSkill.LLM_TO_ANSWER_EASY_QUESTIONS,
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate with settings",
            model=LLMSkill.LLM_TO_ANSWER_EASY_QUESTIONS,
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
            llm_skill=LLMSkill.LLM_TO_ANALYZE_DATA,
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate with system prompt",
            inputs={"data": "Data"},
            system_prompt="You are a data analyst",
            prompt="Analyze: @data",
            output="Analysis",
            model=LLMSkill.LLM_TO_ANALYZE_DATA,
        ),
    )

    LLM_WITH_MULTIPLE_OUTPUT = (
        "llm_with_multiple_output",
        PipeLLMSpec(
            pipe_code="generate_items",
            description="Generate multiple items",
            inputs={},
            output="Item[]",
            prompt="Generate items",
            llm_skill=LLMSkill.LLM_TO_ANSWER_EASY_QUESTIONS,
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate multiple items",
            output="Item[]",
            prompt="Generate items",
            model=LLMSkill.LLM_TO_ANSWER_EASY_QUESTIONS,
        ),
    )

    LLM_WITH_FIXED_OUTPUT = (
        "llm_with_fixed_output",
        PipeLLMSpec(
            pipe_code="generate_items",
            description="Generate exactly 5 items",
            inputs={},
            output="Item[5]",
            prompt="Generate items",
            llm_skill=LLMSkill.LLM_TO_ANSWER_EASY_QUESTIONS,
        ),
        PipeLLMBlueprint(
            source=None,
            type="PipeLLM",
            description="Generate exactly 5 items",
            output="Item[5]",
            prompt="Generate items",
            model=LLMSkill.LLM_TO_ANSWER_EASY_QUESTIONS,
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
