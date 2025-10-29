from pipelex.exceptions import PipelexException


class DomainError(PipelexException):
    pass


class DomainCodeError(DomainError):
    pass


class DomainDefinitionError(PipelexException):
    def __init__(self, message: str, domain_code: str, description: str, source: str | None = None):
        self.domain_code = domain_code
        self.description = description
        self.source = source
        super().__init__(message)
