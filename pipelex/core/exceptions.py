from pydantic import BaseModel
from typing_extensions import override

from pipelex.base_exceptions import PipelexException
from pipelex.core.pipes.exceptions import StaticValidationErrorType


class PipelexConfigurationError(PipelexException):
    """Raised when there are configuration issues with the PipelexInterpreter."""


class SyntaxErrorData(BaseModel):
    message: str
    lineno: int | None = None
    offset: int | None = None
    text: str | None = None
    end_lineno: int | None = None
    end_offset: int | None = None

    @classmethod
    def from_syntax_error(cls, syntax_error: SyntaxError) -> "SyntaxErrorData":
        return cls(
            message=syntax_error.msg,
            lineno=syntax_error.lineno,
            offset=syntax_error.offset,
            text=syntax_error.text,
            end_lineno=syntax_error.end_lineno,
            end_offset=syntax_error.end_offset,
        )


class StaticValidationError(Exception):
    def __init__(
        self,
        error_type: StaticValidationErrorType,
        domain: str,
        pipe_code: str | None = None,
        variable_names: list[str] | None = None,
        required_concept_codes: list[str] | None = None,
        provided_concept_code: str | None = None,
        file_path: str | None = None,
        explanation: str | None = None,
    ):
        self.error_type = error_type
        self.domain = domain
        self.pipe_code = pipe_code
        self.variable_names = variable_names
        self.required_concept_codes = required_concept_codes
        self.provided_concept_code = provided_concept_code
        self.file_path = file_path
        self.explanation = explanation
        super().__init__()

    def desc(self) -> str:
        msg = f"{self.error_type} • domain='{self.domain}'"
        if self.pipe_code:
            msg += f" • pipe='{self.pipe_code}'"
        if self.variable_names:
            msg += f" • variable='{self.variable_names}'"
        if self.required_concept_codes:
            msg += f" • required_concept_codes='{self.required_concept_codes}'"
        if self.provided_concept_code:
            msg += f" • provided_concept_code='{self.provided_concept_code}'"
        if self.file_path:
            msg += f" • file='{self.file_path}'"
        if self.explanation:
            msg += f" • explanation='{self.explanation}'"
        return msg

    @override
    def __str__(self) -> str:
        return self.desc()
