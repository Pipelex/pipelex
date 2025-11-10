from pipelex.base_exceptions import PipelexException


class DomainCodeError(PipelexException):
    pass


class DomainDefinitionError(PipelexException):
    def __init__(self, message: str, domain_code: str, description: str, source: str | None = None):
        self.domain_code = domain_code
        self.description = description
        self.source = source
        super().__init__(message)
