"""The orchestration-mode axis: *which* orchestrator runs a pipe.

``orchestration_mode`` is an **open string token**, not a closed enum. Core owns
only ``"direct"`` (its single built-in, in-process orchestrator); every other token
is contributed by the plugin that owns the orchestrator — ``pipelex-temporal`` owns
``"temporal"``, ``pipelex-mistralai-workflows`` owns ``"mistralai-workflows"``. The
orchestrator/validator registries are keyed by this token and validation is a
registry lookup (*is this mode registered?* → ``MissingOrchestratorError`` on a miss),
never an enum-membership check.

This is the deliberate, justified exception to the repo's StrEnum-everywhere standard:
that standard exists to make the linter scream when a *closed* value is added and a
branch forgotten, but a plugin-contributed set is genuinely open — exhaustive matching
is impossible, and the dict-lookup-or-raise *is* the correct unknown-handling. It is
also the only choice faithful to "the public base names no orchestrator": a closed
``{DIRECT, TEMPORAL, MISTRAL}`` enum would re-introduce the very core→plugin coupling
the plugin-system externalization removed.

``OrchestrationMode`` is a plain ``str`` alias (not a ``NewType``) so plugins pass raw
string tokens with no casts at the registry boundary — the registry is the validator,
so a ``NewType``'s casts would buy zero validation. The wait-semantics axis lives
separately in :mod:`pipelex.runtime_bridge.delivery_mode` (a closed
``DeliveryMode`` enum) — the two are orthogonal.
"""

from typing import Final, TypeAlias

# A registered orchestration token. A semantic alias documenting intent at registry /
# protocol signatures (``dict[OrchestrationMode, ...]``); assignment-compatible with
# plain ``str`` so a plugin registers under a bare string literal with no cast.
OrchestrationMode: TypeAlias = str

# Core's one built-in token. Core code references this constant rather than the bare
# ``"direct"`` literal; every other token is owned by the plugin that registers it.
DIRECT_ORCHESTRATION_MODE: Final[str] = "direct"
