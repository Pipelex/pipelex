class RootException(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class PipelexException(RootException):
    pass


class PipelexUnexpectedError(PipelexException):
    pass


class PipelexConfigError(PipelexException):
    pass


class PipelexSetupError(PipelexException):
    pass
