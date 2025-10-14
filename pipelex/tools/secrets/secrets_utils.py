import re

from pipelex.hub import get_secrets_provider
from pipelex.system.environment import EnvVarNotFoundError, get_optional_env, get_required_env
from pipelex.system.exceptions import ToolException
from pipelex.tools.secrets.secrets_errors import SecretNotFoundError
from pipelex.types import StrEnum


class VarNotFoundError(ToolException):
    def __init__(self, var_name: str, message: str):
        self.var_name = var_name
        super().__init__(message)


class VarFallbackPatternError(ToolException):
    pass


class UnknownVarPrefixError(ToolException):
    """Raised when an unknown variable prefix is used in variable substitution."""

    def __init__(self, var_name: str, message: str):
        self.var_name = var_name
        super().__init__(message)


class VarPrefix(StrEnum):
    """Variable prefix types for variable substitution."""

    ENV = "env"
    SECRET = "secret"


def substitute_vars(content: str) -> str:
    """Substitute variable placeholders with values from environment variables or secrets.

    Supports the following placeholder formats:
    - ${VAR_NAME} -> use secrets provider by default
    - ${env:ENV_VAR_NAME} -> force use environment variable
    - ${secret:SECRET_NAME} -> force use secrets provider
    - ${env:ENV_VAR_NAME|secret:SECRET_NAME} -> try env first, then secret as fallback

    Args:
        content: Text content with variable placeholders

    Returns:
        Content with variables substituted

    Raises:
        VarNotFoundError: If required variable is missing from all specified sources

    """

    def replace_var(match: re.Match[str]) -> str:
        var_spec = match.group(1)

        # Check if it's a fallback pattern (contains |)
        if "|" in var_spec:
            return _handle_fallback_pattern(var_spec)

        # Check if it has a prefix (env: or secret:)
        if ":" in var_spec:
            prefix_str, var_name = var_spec.split(":", 1)
            prefix_str = prefix_str.strip()

            try:
                prefix = VarPrefix(prefix_str)
            except ValueError as exc:
                msg = f"Unknown variable prefix: '{prefix_str}'"
                raise UnknownVarPrefixError(
                    var_name=var_name,
                    message=msg,
                ) from exc

            match prefix:
                case VarPrefix.ENV:
                    return _get_env_var(var_name)
                case VarPrefix.SECRET:
                    return _get_secret(var_name)
        else:
            # Default behavior: use secrets provider
            return _get_secret(var_spec)

    # Pattern matches ${VAR_NAME} or ${prefix:VAR_NAME} or ${env:VAR|secret:VAR}
    # Restrict to not match across newlines, quotes, or nested braces
    pattern = r"\$\{([^}\n\"'$]+)\}"
    return re.sub(pattern, replace_var, content)


def _handle_fallback_pattern(var_spec: str) -> str:
    """Handle fallback pattern like 'env:VAR|secret:VAR'."""
    parts = [part.strip() for part in var_spec.split("|")]

    for part in parts:
        if ":" in part:
            prefix_str, var_name = part.split(":", 1)
            prefix_str = prefix_str.strip()

            try:
                prefix = VarPrefix(prefix_str)
            except ValueError as exc:
                msg = f"Unknown variable prefix: '{prefix_str}'"
                raise UnknownVarPrefixError(
                    var_name=var_name,
                    message=msg,
                ) from exc

            match prefix:
                case VarPrefix.ENV:
                    value = get_optional_env(var_name)
                    if value is not None:
                        return value
                case VarPrefix.SECRET:
                    try:
                        return get_secrets_provider().get_secret(secret_id=var_name)
                    except SecretNotFoundError:
                        continue  # Try next option
        else:
            # No prefix, try as secret
            try:
                return get_secrets_provider().get_secret(secret_id=part)
            except SecretNotFoundError:
                continue  # Try next option
    msg = f"Could not get variable from fallback pattern: {var_spec}"
    raise VarFallbackPatternError(message=msg)


def _get_env_var(var_name: str) -> str:
    """Get environment variable, raising VarNotFoundError if not found."""
    try:
        return get_required_env(var_name)
    except EnvVarNotFoundError as exc:
        msg = f"Could not get variable '{var_name}': {exc!s}"
        raise VarNotFoundError(message=msg, var_name=var_name) from exc


def _get_secret(secret_name: str) -> str:
    """Get secret, raising VarNotFoundError if not found."""
    try:
        return get_secrets_provider().get_secret(secret_id=secret_name)
    except SecretNotFoundError as exc:
        msg = f"Could not get variable '{secret_name}': {exc!s}"
        raise VarNotFoundError(message=msg, var_name=secret_name) from exc
