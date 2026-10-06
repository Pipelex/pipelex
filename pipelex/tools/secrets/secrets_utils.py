import re
from enum import StrEnum

from pipelex.system.environment import get_optional_env, get_required_env
from pipelex.system.exceptions import EnvVarNotFoundError
from pipelex.tools.secrets.exceptions import (
    SecretNotFoundError,
    UnknownVarPrefixError,
    VarFallbackPatternError,
    VarNotFoundError,
)
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

# A ``${…}`` placeholder: ``${VAR_NAME}``, ``${prefix:VAR_NAME}`` or ``${env:VAR|secret:VAR}``. Restricted so as not to
# match across newlines, quotes or nested braces. Its one group is what sits between the braces.
VAR_PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}\n\"'$]+)\}")


class VarPrefix(StrEnum):
    """Variable prefix types for variable substitution."""

    ENV = "env"
    SECRET = "secret"


def substitute_vars(
    content: str,
    *,
    secrets_provider: SecretsProviderAbstract,
    raise_on_missing_var: bool = True,
) -> str:
    """Substitute variable placeholders with values from environment variables or secrets.

    Supports the following placeholder formats:
    - ${VAR_NAME} -> use secrets provider by default
    - ${env:ENV_VAR_NAME} -> force use environment variable
    - ${secret:SECRET_NAME} -> force use secrets provider
    - ${env:ENV_VAR_NAME|secret:SECRET_NAME} -> try env first, then secret as fallback

    Args:
        content: Text content with variable placeholders
        secrets_provider: The secrets provider to use for secret lookups
        raise_on_missing_var: If True (default), raise VarNotFoundError when a variable
            is not found. If False, keep the original placeholder in the output.

    Returns:
        Content with variables substituted

    Raises:
        VarNotFoundError: If required variable is missing from all specified sources
            and raise_on_missing_var is True

    """

    def replace_var(match: re.Match[str]) -> str:
        var_spec = match.group(1)

        try:
            # Check if it's a fallback pattern (contains |)
            if "|" in var_spec:
                return _handle_fallback_pattern(var_spec, secrets_provider=secrets_provider)

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
                        return _get_secret(var_name, secrets_provider=secrets_provider)
            else:
                # Default behavior: use secrets provider
                return _get_secret(var_spec, secrets_provider=secrets_provider)
        except (VarNotFoundError, VarFallbackPatternError):
            if raise_on_missing_var:
                raise
            return match.group(0)  # Keep original placeholder

    return VAR_PLACEHOLDER_PATTERN.sub(replace_var, content)


def placeholder_var_names(*, content: str) -> list[str]:
    """The names of the variables the placeholders in `content` reference, in order and without repeats.

    Resolves nothing: `${VAR}`, `${env:VAR}`, `${secret:VAR}` and every candidate of a fallback
    pattern such as `${env:VAR|secret:OTHER}` each contribute their name. A prefix this module does
    not know is refused as `substitute_vars` refuses it, so a file that names its variables without
    resolving them gets the same verdict on its syntax as one that resolves them.

    Raises:
        UnknownVarPrefixError: If a placeholder carries a prefix other than `env` or `secret`.
    """
    var_names: list[str] = []
    for match in VAR_PLACEHOLDER_PATTERN.finditer(content):
        for part in match.group(1).split("|"):
            var_name = part
            if ":" in part:
                prefix_str, var_name = part.split(":", 1)
                prefix_str = prefix_str.strip()
                try:
                    VarPrefix(prefix_str)
                except ValueError as exc:
                    raise UnknownVarPrefixError(var_name=var_name.strip(), message=f"Unknown variable prefix: '{prefix_str}'") from exc
            var_name = var_name.strip()
            if var_name not in var_names:
                var_names.append(var_name)
    return var_names


def _handle_fallback_pattern(var_spec: str, *, secrets_provider: SecretsProviderAbstract) -> str:
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
                        return secrets_provider.get_secret(secret_id=var_name)
                    except SecretNotFoundError:
                        continue  # Try next option
        else:
            # No prefix, try as secret
            try:
                return secrets_provider.get_secret(secret_id=part)
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


def _get_secret(secret_name: str, *, secrets_provider: SecretsProviderAbstract) -> str:
    """Get secret, raising VarNotFoundError if not found."""
    try:
        return secrets_provider.get_secret(secret_id=secret_name)
    except SecretNotFoundError as exc:
        msg = f"Could not get variable '{secret_name}': {exc!s}"
        raise VarNotFoundError(message=msg, var_name=secret_name) from exc
