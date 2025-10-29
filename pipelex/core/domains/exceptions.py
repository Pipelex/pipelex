from pipelex.exceptions import PipelexException


class DomainError(PipelexException):
    pass


class DomainCodeError(DomainError):
    pass
