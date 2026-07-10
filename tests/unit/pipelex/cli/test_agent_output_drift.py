"""Drift-detection tests for the agent CLI error lookup dicts.

AGENT_ERROR_HINTS / AGENT_ERROR_DOMAINS / RETRYABLE_ERROR_TYPES are string-keyed
by exception class name (or synthetic error_type label). These tests catch:
- stale keys left behind when an exception class is renamed or deleted;
- a PipelexError subclass that carries class-level metadata yet still has a
  redundant lookup-dict entry (the class must be the single source of truth).
"""

import importlib

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.agent_output import AGENT_ERROR_DOMAINS, AGENT_ERROR_HINTS, RETRYABLE_ERROR_TYPES

# Modules defining every PipelexError subclass referenced by the lookup dicts.
# Imported so PipelexError.__subclasses__() sees them when the registry is built.
_EXCEPTION_MODULES: tuple[str, ...] = (
    "pipelex.codegen.exceptions",
    "pipelex.cogt.exceptions",
    "pipelex.core.interpreter.exceptions",
    "pipelex.core.pipes.exceptions",
    "pipelex.pipe_operators.exceptions",
    "pipelex.pipeline.exceptions",
    "pipelex.pipeline.validate_bundle",
    "pipelex.system.pipelex_service.exceptions",
    "pipelex.system.telemetry.exceptions",
    "pipelex.tools.misc.json_utils",
    "pipelex.tools.misc.toml_utils",
)

# Lookup-dict keys that are intentionally NOT PipelexError subclasses and
# therefore cannot carry class-level metadata:
# - builtin / third-party exception classes
# - synthetic error_type labels passed straight to agent_error(...)
_NON_PIPELEX_ERROR_KEYS: frozenset[str] = frozenset(
    {
        "FileNotFoundError",  # builtin
        "JSONDecodeError",  # json builtin
        "ValueError",  # builtin
        "ValidationError",  # pydantic
        "PipeValidationError",  # subclass of ValueError, not of PipelexError
        "ClientAuthenticationError",  # mthds API client package
        "PipelineRequestError",  # mthds API client package
        "ArgumentError",  # synthetic error_type label
        "BinaryNotFoundError",  # synthetic error_type label
        "GraphSpecParseError",  # synthetic error_type label
        "BundleError",  # synthetic error_type label
        "CodegenDriftError",  # synthetic error_type label (a drift verdict, not an exception)
        "CodegenLockNotFoundError",  # synthetic error_type label
        "InitConfigError",  # synthetic error_type label
        "UnknownCommandError",  # synthetic error_type label
    }
)


def _all_pipelex_error_subclasses() -> set[type[PipelexError]]:
    """Return every imported PipelexError subclass, walking the hierarchy recursively."""
    for module_name in _EXCEPTION_MODULES:
        importlib.import_module(module_name)
    collected: set[type[PipelexError]] = set()
    pending: list[type[PipelexError]] = [PipelexError]
    while pending:
        current = pending.pop()
        for subclass in current.__subclasses__():
            if subclass not in collected:
                collected.add(subclass)
                pending.append(subclass)
    return collected


class TestAgentOutputDrift:
    """Guards the agent CLI lookup dicts against class renames and redundant entries."""

    def test_every_dict_key_is_a_known_error_type(self) -> None:
        """Every lookup-dict key resolves to a PipelexError subclass or a documented non-PipelexError type."""
        known_pipelex_names = {cls.__name__ for cls in _all_pipelex_error_subclasses()}
        all_keys = set(AGENT_ERROR_HINTS) | set(AGENT_ERROR_DOMAINS) | set(RETRYABLE_ERROR_TYPES)
        for key in all_keys:
            assert key in known_pipelex_names or key in _NON_PIPELEX_ERROR_KEYS, (
                f"Lookup-dict key {key!r} is neither a known PipelexError subclass nor a documented "
                f"non-PipelexError type — likely a stale entry after a rename or delete."
            )

    def test_class_level_error_domain_not_duplicated_in_dict(self) -> None:
        """A subclass that declares class-level error_domain must not also sit in AGENT_ERROR_DOMAINS."""
        for cls in _all_pipelex_error_subclasses():
            if cls.error_domain is not None:
                assert cls.__name__ not in AGENT_ERROR_DOMAINS, (
                    f"{cls.__name__} carries a class-level error_domain; its AGENT_ERROR_DOMAINS entry "
                    f"is redundant — remove it so the class is the single source of truth."
                )

    def test_class_level_user_action_not_duplicated_in_dict(self) -> None:
        """A subclass that declares class-level user_action must not also sit in AGENT_ERROR_HINTS."""
        for cls in _all_pipelex_error_subclasses():
            if cls.user_action is not None:
                assert cls.__name__ not in AGENT_ERROR_HINTS, (
                    f"{cls.__name__} carries a class-level user_action; its AGENT_ERROR_HINTS entry "
                    f"is redundant — remove it so the class is the single source of truth."
                )
