from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.system.exceptions import RootException

if TYPE_CHECKING:
    from pipelex.builder.validation_error_data import StaticValidationErrorType


class PipelexException(RootException):
    pass


class PipelexUnexpectedError(PipelexException):
    pass


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


class PipelexConfigError(PipelexException):
    pass


class PipelexSetupError(PipelexException):
    pass
