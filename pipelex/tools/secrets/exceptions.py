from pipelex.system.exceptions import ToolError


class SecretNotFoundError(ToolError):
    pass


class VarNotFoundError(ToolError):
    def __init__(self, var_name: str, message: str):
        self.var_name = var_name
        super().__init__(message)


class VarFallbackPatternError(ToolError):
    pass


class UnknownVarPrefixError(ToolError):
    """Raised when an unknown variable prefix is used in variable substitution."""

    def __init__(self, var_name: str, message: str):
        self.var_name = var_name
        super().__init__(message)
