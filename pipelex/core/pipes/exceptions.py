from pydantic import BaseModel, Field

from pipelex.exceptions import PipelexException


class PipeBlueprintValueError(ValueError):
    pass


class PipeInputNotFoundError(PipelexException):
    pass


class PipeFactoryError(PipelexException):
    pass


class PipeInputError(PipelexException):
    def __init__(self, message: str, pipe_code: str, variable_name: str, concept_code: str | None = None):
        self.pipe_code = pipe_code
        self.variable_name = variable_name
        self.concept_code = concept_code
        super().__init__(message)


class PipeRunInputsError(PipelexException):
    def __init__(self, message: str, pipe_code: str, missing_inputs: dict[str, str]):
        self.pipe_code = pipe_code
        self.missing_inputs = missing_inputs
        super().__init__(message)


class PipeDefinitionErrorData(BaseModel):
    message: str = Field(description="The error message")
    domain_code: str | None = Field(None, description="The domain code")
    pipe_code: str | None = Field(None, description="The pipe code")
    description: str | None = Field(None, description="Description of the pipe")
    source: str | None = Field(None, description="Source of the error")
