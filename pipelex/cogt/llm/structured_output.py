from instructor import Mode as InstructorMode

from pipelex.types import StrEnum


class StructureMethod(StrEnum):
    INSTRUCTOR_OPENAI_STRUCTURED = "openai_structured"
    INSTRUCTOR_ANTHROPIC_TOOLS = "anthropic_tools"
    INSTRUCTOR_MISTRAL_TOOLS = "mistral_tools"
    INSTRUCTOR_VERTEX_JSON = "vertex_json"
    INSTRUCTOR_GENAI_TOOLS = "genai_tools"
    INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS = "genai_structured_outputs"

    def as_instructor_mode(self) -> InstructorMode:
        match self:
            case StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED:
                return InstructorMode.TOOLS_STRICT
            case StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS:
                return InstructorMode.ANTHROPIC_TOOLS
            case StructureMethod.INSTRUCTOR_MISTRAL_TOOLS:
                return InstructorMode.MISTRAL_TOOLS
            case StructureMethod.INSTRUCTOR_VERTEX_JSON:
                return InstructorMode.ANTHROPIC_JSON
            case StructureMethod.INSTRUCTOR_GENAI_TOOLS:
                return InstructorMode.GENAI_TOOLS
            case StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS:
                return InstructorMode.GENAI_STRUCTURED_OUTPUTS
