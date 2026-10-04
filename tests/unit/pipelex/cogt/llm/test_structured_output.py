import warnings

import instructor
import openai
import pytest
from instructor import Mode as InstructorMode
from instructor.v2.core.mode import DEPRECATED_TO_CORE

from pipelex.cogt.llm.structured_output import StructureMethod

# The provider-specific instructor mode each structure method is named after. instructor deprecates all but the
# core ones, because the provider now comes from the client, and resolves each to the core mode it stands for.
LEGACY_INSTRUCTOR_MODES: dict[StructureMethod, InstructorMode] = {
    # generic
    StructureMethod.INSTRUCTOR_JSON: InstructorMode.JSON,
    StructureMethod.INSTRUCTOR_MD_JSON: InstructorMode.MD_JSON,
    StructureMethod.INSTRUCTOR_JSON_SCHEMA: InstructorMode.JSON_SCHEMA,
    # openai
    StructureMethod.INSTRUCTOR_OPENAI_PARALLEL_TOOLS: InstructorMode.PARALLEL_TOOLS,
    StructureMethod.INSTRUCTOR_OPENAI_TOOLS: InstructorMode.TOOLS,
    StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED_OUTPUTS: InstructorMode.TOOLS_STRICT,
    StructureMethod.INSTRUCTOR_OPENAI_JSON_O1: InstructorMode.JSON_O1,
    StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS: InstructorMode.RESPONSES_TOOLS,
    StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS_WITH_INBUILT_TOOLS: InstructorMode.RESPONSES_TOOLS_WITH_INBUILT_TOOLS,
    # anthropic
    StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS: InstructorMode.ANTHROPIC_TOOLS,
    StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS: InstructorMode.ANTHROPIC_REASONING_TOOLS,
    StructureMethod.INSTRUCTOR_ANTHROPIC_JSON: InstructorMode.ANTHROPIC_JSON,
    # mistral
    StructureMethod.INSTRUCTOR_MISTRAL_TOOLS: InstructorMode.MISTRAL_TOOLS,
    StructureMethod.INSTRUCTOR_MISTRAL_STRUCTURED_OUTPUTS: InstructorMode.MISTRAL_STRUCTURED_OUTPUTS,
    # vertexai & google
    StructureMethod.INSTRUCTOR_VERTEXAI_TOOLS: InstructorMode.VERTEXAI_TOOLS,
    StructureMethod.INSTRUCTOR_VERTEXAI_JSON: InstructorMode.VERTEXAI_JSON,
    StructureMethod.INSTRUCTOR_VERTEXAI_PARALLEL_TOOLS: InstructorMode.VERTEXAI_PARALLEL_TOOLS,
    StructureMethod.INSTRUCTOR_GENAI_TOOLS: InstructorMode.GENAI_TOOLS,
    StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS: InstructorMode.GENAI_STRUCTURED_OUTPUTS,
    # cohere
    StructureMethod.INSTRUCTOR_COHERE_TOOLS: InstructorMode.COHERE_TOOLS,
    StructureMethod.INSTRUCTOR_COHERE_JSON_SCHEMA: InstructorMode.COHERE_JSON_SCHEMA,
    # cerebras
    StructureMethod.INSTRUCTOR_CEREBRAS_TOOLS: InstructorMode.CEREBRAS_TOOLS,
    StructureMethod.INSTRUCTOR_CEREBRAS_JSON: InstructorMode.CEREBRAS_JSON,
    # fireworks
    StructureMethod.INSTRUCTOR_FIREWORKS_TOOLS: InstructorMode.FIREWORKS_TOOLS,
    StructureMethod.INSTRUCTOR_FIREWORKS_JSON: InstructorMode.FIREWORKS_JSON,
    # bedrock
    StructureMethod.INSTRUCTOR_BEDROCK_TOOLS: InstructorMode.BEDROCK_TOOLS,
    StructureMethod.INSTRUCTOR_BEDROCK_JSON: InstructorMode.BEDROCK_JSON,
    # other providers
    StructureMethod.INSTRUCTOR_WRITER_TOOLS: InstructorMode.WRITER_TOOLS,
    StructureMethod.INSTRUCTOR_PERPLEXITY_JSON: InstructorMode.PERPLEXITY_JSON,
    StructureMethod.INSTRUCTOR_OPENROUTER_STRUCTURED_OUTPUTS: InstructorMode.OPENROUTER_STRUCTURED_OUTPUTS,
}


class TestStructureMethod:
    def test_legacy_modes_cover_every_member(self):
        """Completeness guard: a new StructureMethod member must be added to the legacy mapping."""
        assert set(LEGACY_INSTRUCTOR_MODES) == set(StructureMethod)

    @pytest.mark.parametrize(
        ("structure_method", "legacy_mode"),
        list(LEGACY_INSTRUCTOR_MODES.items()),
        ids=[str(member) for member in LEGACY_INSTRUCTOR_MODES],
    )
    def test_as_instructor_mode_is_the_core_mode_instructor_resolves_it_to(self, structure_method: StructureMethod, legacy_mode: InstructorMode):
        """Each structure method maps to the core mode instructor itself resolves its provider-specific mode to."""
        assert structure_method.as_instructor_mode() is DEPRECATED_TO_CORE.get(legacy_mode, legacy_mode)

    @pytest.mark.parametrize("structure_method", list(StructureMethod), ids=[str(member) for member in StructureMethod])
    def test_every_structure_method_is_accepted_on_the_openai_sdk(self, structure_method: StructureMethod):
        """A gateway serves every model through an OpenAI client, whichever provider's method its spec names.

        instructor refuses another provider's mode on an OpenAI client, and warns on a deprecated one.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            instructor.from_openai(client=openai.AsyncOpenAI(api_key="unused"), mode=structure_method.as_instructor_mode())
