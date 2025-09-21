"""
Test data for PipeLLMBlueprint conversion tests.
"""

from typing import Any, ClassVar, Dict, List, Tuple

from pipelex.libraries.pipelines.builder.pipe.pipe_llm import LLMSetting, PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import StructuringMethod


class PipeLLMTestCases:
    """Test cases for PipeLLMBlueprint conversion."""

    SIMPLE_LLM = (
        "simple_llm",
        PipeLLMBlueprint(
            definition="Generate text",
            inputs={"topic": "Text"},
            output="Text",
            prompt_template="Write about $topic",
        ),
        "test_pipe",
        "test_domain",
        {
            "type": "PipeLLM",
            "definition": "Generate text",
            "output": "Text",
            "prompt_template": "Write about $topic",
            "inputs_count": 1,
        },
    )

    LLM_NO_INPUTS = (
        "llm_no_inputs",
        PipeLLMBlueprint(
            definition="Generate without inputs",
            inputs={},
            output="Text",
            prompt_template="Generate something interesting",
        ),
        "generate_pipe",
        "test_domain",
        {
            "type": "PipeLLM",
            "definition": "Generate without inputs",
            "output": "Text",
            "prompt_template": "Generate something interesting",
            "inputs_count": 0,
        },
    )

    LLM_WITH_PRESET = (
        "llm_with_preset",
        PipeLLMBlueprint(
            definition="Generate with preset",
            inputs={},
            output="Text",
            prompt_template="Generate text",
            llm="llm_to_reason",
        ),
        "generate",
        "test_domain",
        {
            "type": "PipeLLM",
            "llm": "llm_to_reason",
            "llm_type": "str",
        },
    )

    LLM_WITH_SETTINGS = (
        "llm_with_settings",
        PipeLLMBlueprint(
            definition="Generate with settings",
            inputs={},
            output="Text",
            prompt_template="Generate text",
            llm=LLMSetting(
                llm_handle="gpt-4o-mini",
                temperature=0.7,
                max_tokens=None,  # "auto" is handled at conversion to core
            ),
        ),
        "generate",
        "test_domain",
        {
            "type": "PipeLLM",
            "llm_type": "object",
            "llm_handle": "gpt-4o-mini",
            "llm_temperature": 0.7,
            # max_tokens is None in builder, becomes "auto" in core conversion
        },
    )

    LLM_WITH_SYSTEM_PROMPT = (
        "llm_with_system_prompt",
        PipeLLMBlueprint(
            definition="Generate with system prompt",
            inputs={"data": "Data"},
            output="Analysis",
            system_prompt="You are a data analyst",
            prompt_template="Analyze: @data",
        ),
        "analyze",
        "test_domain",
        {
            "type": "PipeLLM",
            "system_prompt": "You are a data analyst",
            "prompt_template": "Analyze: @data",
        },
    )

    LLM_WITH_MULTIPLE_OUTPUT = (
        "llm_with_multiple_output",
        PipeLLMBlueprint(
            definition="Generate multiple items",
            inputs={},
            output="Item",
            prompt_template="Generate items",
            multiple_output=True,
        ),
        "generate_items",
        "test_domain",
        {
            "type": "PipeLLM",
            "multiple_output": True,
            "nb_output": None,
        },
    )

    LLM_WITH_FIXED_OUTPUT = (
        "llm_with_fixed_output",
        PipeLLMBlueprint(
            definition="Generate exactly 5 items",
            inputs={},
            output="Item",
            prompt_template="Generate items",
            nb_output=5,
        ),
        "generate_five",
        "test_domain",
        {
            "type": "PipeLLM",
            "nb_output": 5,
            "multiple_output": None,
        },
    )

    LLM_WITH_STRUCTURING = (
        "llm_with_structuring",
        PipeLLMBlueprint(
            definition="Extract structured data",
            inputs={},
            output="PersonInfo",
            prompt_template="Extract person info",
            llm="llm_to_extract",
            llm_to_structure=LLMSetting(
                llm_handle="claude-3-sonnet",
                temperature=0.1,
                max_tokens=None,  # "auto" is handled at conversion to core
            ),
            structuring_method=StructuringMethod.PRELIMINARY_TEXT,
            prompt_template_to_structure="Structure the output",
            system_prompt_to_structure="You are a data structurer",
        ),
        "extract",
        "test_domain",
        {
            "type": "PipeLLM",
            "structuring_method": "preliminary_text",
            "prompt_template_to_structure": "Structure the output",
            "system_prompt_to_structure": "You are a data structurer",
            "llm_to_structure_type": "object",
        },
    )

    TEST_CASES: ClassVar[List[Tuple[str, PipeLLMBlueprint, str, str, Dict[str, Any]]]] = [
        SIMPLE_LLM,
        LLM_NO_INPUTS,
        LLM_WITH_PRESET,
        LLM_WITH_SETTINGS,
        LLM_WITH_SYSTEM_PROMPT,
        LLM_WITH_MULTIPLE_OUTPUT,
        LLM_WITH_FIXED_OUTPUT,
        LLM_WITH_STRUCTURING,
    ]
