from __future__ import annotations

from pipelex.system.exceptions import RootException


class PipelexException(RootException):
    pass


class PipelexUnexpectedError(PipelexException):
    pass


class PipelexConfigError(PipelexException):
    pass


class PipelexSetupError(PipelexException):
    pass
