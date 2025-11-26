class PipelexError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class PipelexUnexpectedError(PipelexError):
    pass


class PipelexConfigError(PipelexError):
    pass


class PipelexSetupError(PipelexError):
    pass
