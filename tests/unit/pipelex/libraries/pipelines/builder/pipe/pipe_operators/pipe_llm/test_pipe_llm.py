"""
Test suite for PipeLLMBlueprint.to_core_blueprint conversion method.
"""

from typing import Any, Dict

import pytest

from pipelex.cogt.llm.llm_setting import LLMSetting as LLMSettingCore
from pipelex.libraries.pipelines.builder.pipe.pipe_llm_builder import PipeLLMBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint as PipeLLMBlueprintCore

from .test_data import PipeLLMTestCases


class TestPipeLLMBlueprintConversion:
    """Test PipeLLMBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected",
        PipeLLMTestCases.TEST_CASES,
    )
    def test_pipe_llm_to_core(self, test_name: str, pipe_blueprint: PipeLLMBlueprint, pipe_code: str, domain: str, expected: Dict[str, Any]):
        """Test converting PipeLLM blueprints to core blueprints."""
        # Perform conversion
        core_pipe = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)

        # Basic assertions
        assert isinstance(core_pipe, PipeLLMBlueprintCore)
        assert core_pipe.type == "PipeLLM"

        # Check expected fields
        if "definition" in expected:
            assert core_pipe.definition == expected["definition"]

        if "output" in expected:
            assert core_pipe.output == expected["output"]

        if "prompt_template" in expected:
            assert core_pipe.prompt_template == expected["prompt_template"]

        if "system_prompt" in expected:
            assert core_pipe.system_prompt == expected["system_prompt"]

        if "inputs_count" in expected:
            if expected["inputs_count"] == 0:
                assert core_pipe.inputs is None or (core_pipe.inputs is not None and len(core_pipe.inputs) == 0)
            else:
                assert core_pipe.inputs is not None and len(core_pipe.inputs) == expected["inputs_count"]

        # Check LLM settings
        if "llm_type" in expected:
            if expected["llm_type"] == "str":
                assert isinstance(core_pipe.llm, str)
                assert core_pipe.llm == expected["llm"]
            elif expected["llm_type"] == "object":
                assert isinstance(core_pipe.llm, LLMSettingCore)
                if "llm_handle" in expected:
                    assert core_pipe.llm.llm_handle == expected["llm_handle"]
                if "llm_temperature" in expected:
                    assert core_pipe.llm.temperature == expected["llm_temperature"]
                if "llm_max_tokens" in expected:
                    assert core_pipe.llm.max_tokens == expected["llm_max_tokens"]

        # Check output settings
        if "multiple_output" in expected:
            assert core_pipe.multiple_output == expected["multiple_output"]

        if "nb_output" in expected:
            assert core_pipe.nb_output == expected["nb_output"]

        # Check structuring settings
        if "structuring_method" in expected:
            assert core_pipe.structuring_method == expected["structuring_method"]

        if "prompt_template_to_structure" in expected:
            assert core_pipe.prompt_template_to_structure == expected["prompt_template_to_structure"]

        if "system_prompt_to_structure" in expected:
            assert core_pipe.system_prompt_to_structure == expected["system_prompt_to_structure"]

        if "llm_to_structure_type" in expected:
            if expected["llm_to_structure_type"] == "object":
                assert isinstance(core_pipe.llm_to_structure, LLMSettingCore)
