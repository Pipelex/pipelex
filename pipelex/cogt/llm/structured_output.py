from instructor import Mode as InstructorMode

from pipelex.types import StrEnum


class StructureMethod(StrEnum):
    INSTRUCTOR_TOOLS = "tools"
    INSTRUCTOR_TOOLS_STRICT = "tools_strict"
    INSTRUCTOR_JSON_O1 = "json_o1"
    INSTRUCTOR_ANTHROPIC_TOOLS = "anthropic_tools"
    INSTRUCTOR_MISTRAL_TOOLS = "mistral_tools"
    INSTRUCTOR_VERTEXAI_TOOLS = "vertexai_tools"
    INSTRUCTOR_VERTEXAI_JSON = "vertexai_json"
    INSTRUCTOR_GENAI_TOOLS = "genai_tools"
    INSTRUCTOR_GROQ_TOOLS = "groq_tools"
    INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS = "genai_structured_outputs"

    def as_instructor_mode(self) -> InstructorMode:
        match self:
            case StructureMethod.INSTRUCTOR_TOOLS:
                return InstructorMode.TOOLS
            case StructureMethod.INSTRUCTOR_TOOLS_STRICT:
                return InstructorMode.TOOLS_STRICT
            case StructureMethod.INSTRUCTOR_JSON_O1:
                return InstructorMode.JSON_O1
            case StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS:
                return InstructorMode.ANTHROPIC_TOOLS
            case StructureMethod.INSTRUCTOR_MISTRAL_TOOLS:
                return InstructorMode.MISTRAL_TOOLS
            case StructureMethod.INSTRUCTOR_VERTEXAI_TOOLS:
                return InstructorMode.VERTEXAI_TOOLS
            case StructureMethod.INSTRUCTOR_VERTEXAI_JSON:
                return InstructorMode.ANTHROPIC_JSON
            case StructureMethod.INSTRUCTOR_GENAI_TOOLS:
                return InstructorMode.GENAI_TOOLS
            case StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS:
                return InstructorMode.GENAI_STRUCTURED_OUTPUTS
            case StructureMethod.INSTRUCTOR_GROQ_TOOLS:
                return InstructorMode.JSON
