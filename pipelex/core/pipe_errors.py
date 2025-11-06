from pipelex.system.exceptions import RootException


# TODO: add details from all cases raising this error
class PipeDefinitionError(RootException):
    def __init__(
        self,
        message: str,
        domain_code: str | None = None,
        pipe_code: str | None = None,
        description: str | None = None,
        source: str | None = None,
    ):
        self.domain_code = domain_code
        self.pipe_code = pipe_code
        self.description = description
        self.source = source
        message = message + " • " + self.pipe_details()
        super().__init__(message)

    def pipe_details(self) -> str:
        if not self.domain_code and not self.pipe_code and not self.description and not self.source:
            return "No pipe details provided"
        details = "Pipe details:"
        if self.domain_code:
            details += f" • domain='{self.domain_code}'"
        if self.pipe_code:
            details += f" • pipe='{self.pipe_code}'"
        if self.description:
            details += f" • description='{self.description}'"
        if self.source:
            details += f" • source='{self.source}'"
        return details


class UnexpectedPipeDefinitionError(PipeDefinitionError):
    pass
