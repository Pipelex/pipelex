"""Drift-detection tests for the agent CLI error lookup dicts.

AGENT_ERROR_HINTS / AGENT_ERROR_DOMAINS are string-keyed by exception class name (or
synthetic error_type label). These tests catch:
- stale keys left behind when an exception class is renamed or deleted;
- a PipelexError subclass in AGENT_ERROR_DOMAINS, whose entry can never be read: every
  PipelexError carries a registry code, and the report's domain is that code's.
"""

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.agent_output import AGENT_ERROR_DOMAINS, AGENT_ERROR_HINTS
from pipelex.errors.error_class_discovery import iter_pipelex_error_subclasses

# Lookup-dict keys that are intentionally NOT PipelexError subclasses and
# therefore carry no registry code:
# - builtin / third-party exception classes
# - synthetic error_type labels passed straight to agent_error(...)
_NON_PIPELEX_ERROR_KEYS: frozenset[str] = frozenset(
    {
        "FileNotFoundError",  # builtin
        "JSONDecodeError",  # json builtin
        "ValueError",  # builtin
        "ValidationError",  # pydantic
        "ArgumentError",  # synthetic error_type label
        "BinaryNotFoundError",  # synthetic error_type label
        "FixBundleError",  # synthetic error_type label
        "BundleError",  # synthetic error_type label
        "CodegenDriftError",  # synthetic error_type label (a drift verdict, not an exception)
        "CodegenLockNotFoundError",  # synthetic error_type label
        "InitConfigError",  # synthetic error_type label
        "StdinEnvelopeShapeError",  # synthetic error_type label
        "UnknownCommandError",  # synthetic error_type label
    }
)


def _pipelex_error_names() -> set[str]:
    """The name of every PipelexError subclass, every error module force-loaded."""
    return {cls.__name__ for cls in iter_pipelex_error_subclasses() if cls is not PipelexError}


class TestAgentOutputDrift:
    """Guards the agent CLI lookup dicts against class renames and unreadable entries."""

    def test_every_dict_key_is_a_known_error_type(self) -> None:
        """Every lookup-dict key resolves to a PipelexError subclass or a documented non-PipelexError type."""
        known_pipelex_names = _pipelex_error_names()
        for key in set(AGENT_ERROR_HINTS) | set(AGENT_ERROR_DOMAINS):
            assert key in known_pipelex_names or key in _NON_PIPELEX_ERROR_KEYS, (
                f"Lookup-dict key {key!r} is neither a known PipelexError subclass nor a documented "
                f"non-PipelexError type — likely a stale entry after a rename or delete."
            )

    def test_no_documented_non_pipelex_key_is_a_pipelex_error(self) -> None:
        """A key documented as carrying no code must not name a PipelexError subclass, which carries one."""
        joined = sorted(_NON_PIPELEX_ERROR_KEYS & _pipelex_error_names())
        assert not joined, f"These keys now name PipelexError subclasses; drop them from _NON_PIPELEX_ERROR_KEYS: {joined}"

    def test_no_pipelex_error_has_a_domain_entry(self) -> None:
        """A PipelexError subclass's domain is its code's, so an AGENT_ERROR_DOMAINS entry for it is never read."""
        offenders = sorted(set(AGENT_ERROR_DOMAINS) & _pipelex_error_names())
        assert not offenders, (
            f"These AGENT_ERROR_DOMAINS keys name PipelexError subclasses, whose report carries the domain of their code: "
            f"{offenders}. Remove the entries; if the domain is wrong, the class needs another code."
        )

    def test_class_level_user_action_not_duplicated_in_dict(self) -> None:
        """A subclass that declares class-level user_action must not also sit in AGENT_ERROR_HINTS."""
        for cls in iter_pipelex_error_subclasses():
            if cls.user_action is not None:
                assert cls.__name__ not in AGENT_ERROR_HINTS, (
                    f"{cls.__name__} carries a class-level user_action; its AGENT_ERROR_HINTS entry "
                    f"is redundant — remove it so the class is the single source of truth."
                )
