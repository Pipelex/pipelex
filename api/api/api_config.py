"""Pipelex-API deployment config: the top-level orchestration mode + override policy.

The runner is orchestrator-agnostic. WHICH orchestrator a top-level run dispatches
to — ``direct`` in-process (the base default), ``temporal``, ``mistral-workflows``,
… — is a *deployment* choice, never a property of this source-available base.
``orchestration_mode`` is an open string token (core owns ``"direct"``; each plugin
owns its own); the *delivery* axis (blocking vs fire-and-forget) is endpoint-set, not
configured here. It is read from a packaged ``api.toml`` (keys at the file root — no
``[api]`` wrapper, since :meth:`load_plugin_config` validates the whole document
against the schema, exactly like ``temporal.toml``), env-layered like the main pipelex
config and every plugin config (D2): the packaged default ``api.toml`` (shipped in this
wheel) is deep-merged with the env-selected ``api_{environment}.toml`` and
``api_override.toml`` from ``~/.pipelex`` then the project ``.pipelex``, with
``PIPELEX_ENV`` (``runtime_manager.environment``) choosing the env file. One image
bakes every env file; a deployment flavor (e.g. ``pipelex-api-hosted``) bakes
``.pipelex/api_{env}.toml`` to flip the default. The base names no orchestrator and
ships ``orchestration_mode = "direct"``.

Why a separate ``api.toml`` and not the core ``pipelex_{env}.toml``: core's
config is ``extra="forbid"``, so an ``[api]`` section there is rejected at load.
Loading it via core's reusable :meth:`load_plugin_config` keeps this a pure
pipelex-api concern while reusing the identical env-layering machinery — and
keeps it symmetric with how ``pipelex-temporal`` self-loads ``temporal.toml``.
"""

from functools import cache
from pathlib import Path

from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE
from pipelex.system.configuration.config_loader import config_manager
from pydantic import BaseModel, ConfigDict

from api.error_types import ErrorType
from api.errors import raise_forbidden

API_CONFIG_NAME = "api"

# The packaged default ``api.toml`` ships in the wheel alongside this module.
_PACKAGE_DIR = Path(__file__).resolve().parent


class ApiConfig(BaseModel):
    """The ``[api]`` deployment config: default orchestration mode + override policy.

    No field defaults — the packaged ``api.toml`` is the single source of the
    base defaults (mirroring core's "defaults live in the TOML, never in the
    model" discipline). ``extra="forbid"`` so a typo'd key in a baked override
    fails loud at load instead of being silently ignored.

    ``orchestration_mode`` is an open string token (core owns ``"direct"``; each
    plugin owns its own). It is NOT validated against a closed enum here — an
    unregistered token is refused at dispatch by ``MissingOrchestratorError``,
    the single validation point. The delivery axis (blocking vs fire-and-forget)
    is endpoint-set, never configured, so nothing about wait-semantics lives here.
    """

    model_config = ConfigDict(extra="forbid")

    orchestration_mode: str
    allow_request_orchestration_mode_override: bool


def load_api_config() -> ApiConfig:
    """Load the ``[api]`` config from ``api.toml`` with env-aware layering (D2).

    Delegates to core's reusable plugin-config loader: the packaged ``api.toml``
    is deep-merged with the env-selected overrides. The packaged default alone is
    a valid, fully-resolved config — every override tier is optional. Requires
    Pipelex to be booted (``runtime_manager.environment`` must be resolved), so
    it is called only after ``Pipelex.make`` — never at import.
    """
    return config_manager.load_plugin_config(name=API_CONFIG_NAME, package_dir=_PACKAGE_DIR, schema=ApiConfig)


@cache
def get_api_config() -> ApiConfig:
    """Process-cached :class:`ApiConfig`.

    The config is immutable for the life of the process (``PIPELEX_ENV`` is fixed
    at boot), so it is loaded once and cached. ``api.main`` warms this at startup
    so a malformed ``api.toml`` / baked override fails the app fast — the same
    fail-fast posture as ``ERROR_DISCLOSURE``. Tests that need a different mode
    patch this getter (or call :func:`resolve_orchestration_mode` with a hand-built
    config) rather than mutating the cache.
    """
    return load_api_config()


def resolve_orchestration_mode(requested: str | None, *, config: ApiConfig) -> str:
    """Resolve the effective orchestration mode for a top-level run, applying policy.

    The deployment default (``config.orchestration_mode``) wins unless the caller
    supplied a *different* token AND the deployment opted into per-request
    override (``allow_request_orchestration_mode_override``). A caller-supplied
    token equal to the default is always honored (it changes nothing). A caller
    trying to FORCE a different mode on a runner whose policy forbids it is refused
    with a 403 — so a locked-down Temporal runner can never be coerced into
    ``direct`` (whose whole point would be to bypass distributed execution), and
    vice versa. The token is a plain string compare; an *unregistered* token is
    not rejected here — that surfaces at dispatch as ``MissingOrchestratorError``.
    """
    if requested is None or requested == config.orchestration_mode:
        return config.orchestration_mode
    if config.allow_request_orchestration_mode_override:
        return requested
    msg = (
        f"This deployment does not allow overriding orchestration_mode per request "
        f"(configured mode '{config.orchestration_mode}', requested '{requested}')."
    )
    raise_forbidden(msg, error_type=ErrorType.ORCHESTRATION_MODE_OVERRIDE_FORBIDDEN)


class ApiBootConfigError(ValueError):
    """Raised at startup when the deployment's orchestration config cannot boot coherently."""


def resolve_boot_orchestrator(config: ApiConfig) -> str | None:
    """The orchestrator plugin this process boots under, derived from the deployment config.

    The base ``direct`` mode names no orchestrator and boots in-process (``None``); any other
    mode (a plugin token like ``"temporal"``) boots the process under that orchestrator so its
    execution-hub slots are claimed and async dispatch is enabled.

    A process boots under exactly one orchestrator, so a ``direct`` default that ALSO enables
    per-request override is incoherent: no async hub is claimed at boot, yet
    :func:`resolve_orchestration_mode` would honor a request overriding to a non-direct mode and
    resolve that orchestrator's dispatch arm — which then fails at dispatch with
    ``AsyncExecutionNotEnabledError``. Refuse it here: fail loud at boot, where the operator sees
    it, rather than on the first overriding request. The mirror case (a non-direct default with
    override on) IS coherent — the async hub is claimed at boot, and a per-request ``direct``
    override still runs in-process — so it boots normally under that orchestrator.
    """
    mode = config.orchestration_mode
    if config.allow_request_orchestration_mode_override and mode == DIRECT_ORCHESTRATION_MODE:
        msg = (
            "allow_request_orchestration_mode_override=true with a 'direct' orchestration_mode default "
            "cannot service a non-direct per-request override: no async execution hub is claimed at boot, "
            "so such a request would fail at dispatch. Set a non-direct orchestration_mode default or "
            "disable per-request override."
        )
        raise ApiBootConfigError(msg)
    if mode == DIRECT_ORCHESTRATION_MODE:
        return None
    return mode
