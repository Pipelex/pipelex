from instructor import Mode as InstructorMode

from pipelex.types import StrEnum


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

    def as_instructor_mode(self) -> InstructorMode:
        match self:
            # generic
            case StructureMethod.INSTRUCTOR_JSON:
                return InstructorMode.JSON
            case StructureMethod.INSTRUCTOR_MD_JSON:
                return InstructorMode.MD_JSON
            case StructureMethod.INSTRUCTOR_JSON_SCHEMA:
                return InstructorMode.JSON_SCHEMA
            # openai
            case StructureMethod.INSTRUCTOR_OPENAI_PARALLEL_TOOLS:
                return InstructorMode.PARALLEL_TOOLS
            case StructureMethod.INSTRUCTOR_OPENAI_TOOLS:
                return InstructorMode.TOOLS
            case StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED_OUTPUTS:
                return InstructorMode.TOOLS_STRICT
            case StructureMethod.INSTRUCTOR_OPENAI_JSON_O1:
                return InstructorMode.JSON_O1
            case StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS:
                return InstructorMode.RESPONSES_TOOLS
            case StructureMethod.INSTRUCTOR_OPENAI_RESPONSES_TOOLS_WITH_INBUILT_TOOLS:
                return InstructorMode.RESPONSES_TOOLS_WITH_INBUILT_TOOLS
            # anthropic
            case StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS:
                return InstructorMode.ANTHROPIC_TOOLS
            case StructureMethod.INSTRUCTOR_ANTHROPIC_REASONING_TOOLS:
                return InstructorMode.ANTHROPIC_REASONING_TOOLS
            case StructureMethod.INSTRUCTOR_ANTHROPIC_JSON:
                return InstructorMode.ANTHROPIC_JSON
            # mistral
            case StructureMethod.INSTRUCTOR_MISTRAL_TOOLS:
                return InstructorMode.MISTRAL_TOOLS
            case StructureMethod.INSTRUCTOR_MISTRAL_STRUCTURED_OUTPUTS:
                return InstructorMode.MISTRAL_STRUCTURED_OUTPUTS
            # vertexai & google
            case StructureMethod.INSTRUCTOR_VERTEXAI_TOOLS:
                return InstructorMode.VERTEXAI_TOOLS
            case StructureMethod.INSTRUCTOR_VERTEXAI_JSON:
                return InstructorMode.VERTEXAI_JSON
            case StructureMethod.INSTRUCTOR_VERTEXAI_PARALLEL_TOOLS:
                return InstructorMode.VERTEXAI_PARALLEL_TOOLS
            case StructureMethod.INSTRUCTOR_GENAI_TOOLS:
                return InstructorMode.GENAI_TOOLS
            case StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS:
                return InstructorMode.GENAI_STRUCTURED_OUTPUTS
            # cohere
            case StructureMethod.INSTRUCTOR_COHERE_TOOLS:
                return InstructorMode.COHERE_TOOLS
            case StructureMethod.INSTRUCTOR_COHERE_JSON_SCHEMA:
                return InstructorMode.COHERE_JSON_SCHEMA
            # cerebras
            case StructureMethod.INSTRUCTOR_CEREBRAS_TOOLS:
                return InstructorMode.CEREBRAS_TOOLS
            case StructureMethod.INSTRUCTOR_CEREBRAS_JSON:
                return InstructorMode.CEREBRAS_JSON
            # fireworks
            case StructureMethod.INSTRUCTOR_FIREWORKS_TOOLS:
                return InstructorMode.FIREWORKS_TOOLS
            case StructureMethod.INSTRUCTOR_FIREWORKS_JSON:
                return InstructorMode.FIREWORKS_JSON
            # bedrock
            case StructureMethod.INSTRUCTOR_BEDROCK_TOOLS:
                return InstructorMode.BEDROCK_TOOLS
            case StructureMethod.INSTRUCTOR_BEDROCK_JSON:
                return InstructorMode.BEDROCK_JSON
            # other providers
            case StructureMethod.INSTRUCTOR_WRITER_TOOLS:
                return InstructorMode.WRITER_TOOLS
            case StructureMethod.INSTRUCTOR_PERPLEXITY_JSON:
                return InstructorMode.PERPLEXITY_JSON
            case StructureMethod.INSTRUCTOR_OPENROUTER_STRUCTURED_OUTPUTS:
                return InstructorMode.OPENROUTER_STRUCTURED_OUTPUTS
