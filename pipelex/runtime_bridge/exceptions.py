from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet, InheritsCause
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE, OrchestrationMode


class PipelexRuntimeBridgeError(PipelexError):
    """Base for errors raised by the Pipelex runtime-bridge surface."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class MissingOrchestratorError(PipelexRuntimeBridgeError):
    """Raised when no orchestrator is registered for a requested orchestration mode.

    ``orchestration_mode`` is an open token: ``"direct"`` is contributed by core, and every
    other token by the plugin that owns its orchestrator (``"temporal"`` →
    our Temporal plugin, ``"mistral-workflows"`` → our Mistral Workflows plugin). A
    lookup miss therefore means *that mode's plugin is not installed* — the message is
    generic and names no orchestrator, so core stays fully decoupled from its plugins. The
    one special case is ``"direct"``: its orchestrator is core and always present, so a miss
    is a boot/discovery fault, not a missing plugin.
    """

    # A mode the deployment configured is its plugin's to install (`pipelex.plugin.not_found`, the default); a
    # mode the caller named and the policy allows is one this runtime does not offer (`runtime.unsupported`); a
    # plugin whose own dependency is absent is `pipelex.config.dependency_missing`. The raise site chooses.
    error_code = ErrorCodeSet(
        default=PipelexErrorCode.PLUGIN_NOT_FOUND,
        others=(CoreCode.RUNTIME_UNSUPPORTED, PipelexErrorCode.CONFIG_DEPENDENCY_MISSING, CoreCode.RUNTIME_UNEXPECTED),
    )

    # The message is caller-actionable ("is its plugin installed?"); keep it under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, mode: OrchestrationMode):
        self.mode = mode
        super().__init__(_build_missing_message(noun="orchestrator", mode=mode))
        _code_a_missing_direct_mode(error=self, mode=mode)


class MissingBundleValidatorError(PipelexRuntimeBridgeError):
    """Raised when no bundle validator is registered for a requested orchestration mode.

    The ``/validate`` counterpart of ``MissingOrchestratorError``: ``"direct"`` is contributed
    by core and every other token by its owning plugin, so a lookup miss means that mode's
    plugin is not installed. The message is generic and names no orchestrator; ``"direct"`` is
    the boot/discovery special case (its validator is core and always present).
    """

    # Split as `MissingOrchestratorError`, by the mode's origin.
    error_code = ErrorCodeSet(
        default=PipelexErrorCode.PLUGIN_NOT_FOUND,
        others=(CoreCode.RUNTIME_UNSUPPORTED, PipelexErrorCode.CONFIG_DEPENDENCY_MISSING, CoreCode.RUNTIME_UNEXPECTED),
    )

    # The message is caller-actionable ("is its plugin installed?"); keep it under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(self, *, mode: OrchestrationMode):
        self.mode = mode
        super().__init__(_build_missing_message(noun="bundle validator", mode=mode))
        _code_a_missing_direct_mode(error=self, mode=mode)


def _build_missing_message(*, noun: str, mode: OrchestrationMode) -> str:
    """Generic, plugin-decoupled message shared by both Missing* errors.

    A plain string compare on ``"direct"`` (not an enum ``match``) — core's one built-in
    token — singles out the boot/discovery fault from the missing-plugin case.
    """
    if mode == DIRECT_ORCHESTRATION_MODE:
        return f"No {noun} is registered for the core '{DIRECT_ORCHESTRATION_MODE}' mode; this indicates a boot or plugin-discovery problem."
    return f"No {noun} is registered for orchestration mode '{mode}'; is its plugin installed?"


def _code_a_missing_direct_mode(*, error: PipelexRuntimeBridgeError, mode: OrchestrationMode) -> None:
    """Choose `runtime.unexpected` for a miss on core's own `"direct"` mode, which is always registered.

    A plain string compare, as in `_build_missing_message`: the miss is a boot or discovery defect of ours,
    never a plugin the deployment forgot.
    """
    if mode == DIRECT_ORCHESTRATION_MODE:
        error.with_error_code(CoreCode.RUNTIME_UNEXPECTED)


class PipelexBridgeDispatchError(PipelexRuntimeBridgeError):
    """Raised when a pipe dispatched through the bridge fails (validation or execution).

    A carrier: it takes the code of the failure it wraps, and `runtime.unexpected` when that failure is not
    a coded error. A raise site with no cause chooses its own: `runtime.unsupported` for fire-and-forget asked
    of a blocking-only orchestrator, `request.invalid` for a host program's malformed dispatch.
    """

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.RUNTIME_UNSUPPORTED, CoreCode.REQUEST_INVALID))
