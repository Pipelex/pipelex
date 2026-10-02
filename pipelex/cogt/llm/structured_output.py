from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from instructor import Mode as InstructorMode


class StructureMethod(StrEnum):
    # generic
    INSTRUCTOR_JSON = "instructor/json"
    INSTRUCTOR_MD_JSON = "instructor/md_json"
    INSTRUCTOR_JSON_SCHEMA = "instructor/json_schema"
    # openai
    INSTRUCTOR_OPENAI_PARALLEL_TOOLS = "instructor/openai_parallel_tools"
    INSTRUCTOR_OPENAI_TOOLS = "instructor/openai_tools"
    INSTRUCTOR_OPENAI_STRUCTURED_OUTPUTS = "instructor/openai_structured_outputs"
    INSTRUCTOR_OPENAI_JSON_O1 = "instructor/openai_json_o1"
    INSTRUCTOR_OPENAI_RESPONSES_TOOLS = "instructor/openai_responses_tools"
    INSTRUCTOR_OPENAI_RESPONSES_TOOLS_WITH_INBUILT_TOOLS = "instructor/openai_responses_tools_with_inbuilt_tools"
    # anthropic
    INSTRUCTOR_ANTHROPIC_TOOLS = "instructor/anthropic_tools"
    INSTRUCTOR_ANTHROPIC_REASONING_TOOLS = "instructor/anthropic_reasoning_tools"
    INSTRUCTOR_ANTHROPIC_JSON = "instructor/anthropic_json"
    # mistral
    INSTRUCTOR_MISTRAL_TOOLS = "instructor/mistral_tools"
    INSTRUCTOR_MISTRAL_STRUCTURED_OUTPUTS = "instructor/mistral_structured_outputs"
    # vertexai & google
    INSTRUCTOR_VERTEXAI_TOOLS = "instructor/vertexai_tools"
    INSTRUCTOR_VERTEXAI_JSON = "instructor/vertexai_json"
    INSTRUCTOR_VERTEXAI_PARALLEL_TOOLS = "instructor/vertexai_parallel_tools"
    INSTRUCTOR_GENAI_TOOLS = "instructor/genai_tools"
    INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS = "instructor/genai_structured_outputs"
    # cohere
    INSTRUCTOR_COHERE_TOOLS = "instructor/cohere_tools"
    INSTRUCTOR_COHERE_JSON_SCHEMA = "instructor/cohere_json_schema"
    # cerebras
    INSTRUCTOR_CEREBRAS_TOOLS = "instructor/cerebras_tools"
    INSTRUCTOR_CEREBRAS_JSON = "instructor/cerebras_json"
    # fireworks
    INSTRUCTOR_FIREWORKS_TOOLS = "instructor/fireworks_tools"
    INSTRUCTOR_FIREWORKS_JSON = "instructor/fireworks_json"
    # bedrock
    INSTRUCTOR_BEDROCK_TOOLS = "instructor/bedrock_tools"
    INSTRUCTOR_BEDROCK_JSON = "instructor/bedrock_json"
    # other providers
    INSTRUCTOR_WRITER_TOOLS = "instructor/writer_tools"
    INSTRUCTOR_PERPLEXITY_JSON = "instructor/perplexity_json"
    INSTRUCTOR_OPENROUTER_STRUCTURED_OUTPUTS = "instructor/openrouter_structured_outputs"

    def as_instructor_mode(self) -> "InstructorMode":
        """The core instructor mode this structure method stands for.

        instructor deprecates its provider-specific modes, because the provider now comes from the client,
        and resolves each one to a core mode, the same one whichever provider it is used with. That
        resolution is done here instead, because an OpenAI client refuses another provider's mode rather
        than resolving it, and a gateway serves every model through an OpenAI client, whichever provider's
        method its spec names.
        """
        from instructor import Mode as InstructorMode  # ruff: ignore[import-outside-top-level]

        match self:
            case (
                StructureMethod.INSTRUCTOR_OPENAI_TOOLS
                | StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED_OUTPUTS
                | StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS
                | StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS
                | StructureMethod.INSTRUCTOR_MISTRAL_TOOLS
                | StructureMethod.INSTRUCTOR_VERTEXAI_TOOLS
                | StructureMethod.INSTRUCTOR_GENAI_TOOLS
                | StructureMethod.INSTRUCTOR_COHERE_TOOLS
                | StructureMethod.INSTRUCTOR_CEREBRAS_TOOLS
                | StructureMethod.INSTRUCTOR_FIREWORKS_TOOLS
                | StructureMethod.INSTRUCTOR_BEDROCK_TOOLS
                | StructureMethod.INSTRUCTOR_WRITER_TOOLS
            ):
                return InstructorMode.TOOLS
            case StructureMethod.INSTRUCTOR_OPENAI_PARALLEL_TOOLS | StructureMethod.INSTRUCTOR_VERTEXAI_PARALLEL_TOOLS:
                return InstructorMode.PARALLEL_TOOLS
            case StructureMethod.INSTRUCTOR_JSON | StructureMethod.INSTRUCTOR_ANTHROPIC_JSON | StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS:
                return InstructorMode.JSON
            case (
                StructureMethod.INSTRUCTOR_MD_JSON
                | StructureMethod.INSTRUCTOR_VERTEXAI_JSON
                | StructureMethod.INSTRUCTOR_CEREBRAS_JSON
                | StructureMethod.INSTRUCTOR_FIREWORKS_JSON
                | StructureMethod.INSTRUCTOR_BEDROCK_JSON
                | StructureMethod.INSTRUCTOR_PERPLEXITY_JSON
            ):
                return InstructorMode.MD_JSON
            case (
                StructureMethod.INSTRUCTOR_JSON_SCHEMA
                | StructureMethod.INSTRUCTOR_OPENAI_JSON_O1
                | StructureMethod.INSTRUCTOR_MISTRAL_STRUCTURED_OUTPUTS
                | StructureMethod.INSTRUCTOR_COHERE_JSON_SCHEMA
                | StructureMethod.INSTRUCTOR_OPENROUTER_STRUCTURED_OUTPUTS
            ):
                return InstructorMode.JSON_SCHEMA
            case StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS | StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS_WITH_INBUILT_TOOLS:
                return InstructorMode.RESPONSES_TOOLS
