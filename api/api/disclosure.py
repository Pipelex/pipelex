"""Resolution of the `ERROR_DISCLOSURE` environment variable.

`ERROR_DISCLOSURE` selects how much of an error report reaches the client:

- `verbose` (default) — the full report, including the human-readable message.
  The intended default for a self-hosted server, where the operator and the
  debugging developer are usually the same person.
- `strict` — the lossy projection pipelex's `DisclosureMode.STRICT` produces,
  for hosted multi-tenant deployments.

The value is resolved once, at app startup (`api.main`). An unrecognized value
fails the app at boot rather than silently degrading — a misconfigured
disclosure mode is a security-relevant mistake the operator must see.
"""

from pipelex.base_exceptions import DisclosureMode
from pipelex.system.environment import get_optional_env

ERROR_DISCLOSURE_ENV_VAR = "ERROR_DISCLOSURE"


class InvalidErrorDisclosureError(ValueError):
    """Raised at startup when `ERROR_DISCLOSURE` holds an unrecognized value."""


def resolve_disclosure_mode() -> DisclosureMode:
    """Resolve `ERROR_DISCLOSURE` to a `DisclosureMode`.

    Returns `DisclosureMode.VERBOSE` when the variable is unset, empty, or
    whitespace-only. Raises `InvalidErrorDisclosureError` for any value other
    than `verbose` or `strict` (matched case-insensitively, surrounding
    whitespace ignored).
    """
    raw = get_optional_env(ERROR_DISCLOSURE_ENV_VAR)
    normalized = (raw or "").strip().lower()
    if not normalized:
        return DisclosureMode.VERBOSE
    try:
        return DisclosureMode(normalized)
    except ValueError as exc:
        valid = ", ".join(f"'{mode}'" for mode in DisclosureMode)
        msg = f"{ERROR_DISCLOSURE_ENV_VAR}={raw!r} is not a valid disclosure mode. Valid values: {valid}."
        raise InvalidErrorDisclosureError(msg) from exc
