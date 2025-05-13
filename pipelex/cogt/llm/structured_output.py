# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from enum import StrEnum

from instructor.mode import Mode as InstructorMode


class StructureMethod(StrEnum):
    INSTRUCTOR_OPENAI_STRUCTURED = "openai_structured"
    INSTRUCTOR_ANTHROPIC_TOOLS = "anthropic_tools"
    INSTRUCTOR_MISTRAL_TOOLS = "mistral_tools"
    INSTRUCTOR_VERTEX_JSON = "vertex_json"

    def as_instructor_mode(self) -> InstructorMode:
        match self:
            case StructureMethod.INSTRUCTOR_OPENAI_STRUCTURED:
                return InstructorMode.TOOLS_STRICT
            case StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS:
                return InstructorMode.ANTHROPIC_TOOLS
            case StructureMethod.INSTRUCTOR_MISTRAL_TOOLS:
                return InstructorMode.MISTRAL_TOOLS
            case StructureMethod.INSTRUCTOR_VERTEX_JSON:
                return InstructorMode.JSON
