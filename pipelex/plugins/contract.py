from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pipelex.plugins.registrar import PluginRegistrar

# The single coarse plugin-API version. A discovered plugin declares the version
# it targets via ``targets_api``; discovery fails loud on a mismatch (see
# ``PluginApiVersionMismatchError``). Bump this only on a breaking change to the
# registrar menu or the plugin contract.
PLUGIN_API_VERSION: int = 1


@runtime_checkable
class PipelexPlugin(Protocol):
    """A unit of optional capability discovered at startup.

    A plugin contributes inference backends, orchestrators, hub-slot claims, CLI
    commands and teardown callbacks by calling the menu methods on the
    ``PluginRegistrar`` it is handed.

    **Invariant — ``register`` is side-effect-free.** It may *only* call
    registrar menu methods: no hub access, no I/O, no SDK/client construction.
    This is what makes ``build_registrar`` safe to run more than once (it runs at
    CLI-build to harvest commands *and* again at boot). Anything heavy — importing
    a backend SDK, constructing a client, importing ``temporalio`` — happens lazily
    inside the ``make_worker`` closures and the hub-slot-claim thunks, never in
    ``register`` itself.
    """

    name: str
    targets_api: int

    def register(self, registrar: "PluginRegistrar") -> None: ...
