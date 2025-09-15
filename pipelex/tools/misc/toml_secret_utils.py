from __future__ import annotations

from typing import Any, Dict

from pipelex.tools.misc.dict_utils import apply_to_strings_recursive
from pipelex.tools.misc.toml_utils import load_toml_from_path
from pipelex.tools.secrets.secrets_utils import UnknownVarPrefixError, VarNotFoundError, substitute_vars


class TOMLSecretValidationError(Exception):
    """Raised when TOML file has formatting issues that could cause problems."""

    pass


def load_toml_from_path_with_secret_substitution(path: str) -> Dict[str, Any]:
    """Load TOML from path with variable substitution.

    Args:
        path: Path to the TOML file

    Returns:
        Dictionary loaded from TOML

    Raises:
        toml.TomlDecodeError: If TOML parsing fails, with file path included
        TOMLValidationError: If variable substitution is enabled and a required variable is missing
    """

    # Parse TOML first
    dict_from_toml = load_toml_from_path(path=path)

    try:
        dict_from_toml = apply_to_strings_recursive(dict_from_toml, substitute_vars)
    except (VarNotFoundError, UnknownVarPrefixError) as exc:
        raise TOMLSecretValidationError(f"Variable substitution failed in file '{path}': {exc}") from exc
    return dict_from_toml
