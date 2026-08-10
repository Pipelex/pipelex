from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pipelex.plugins.registrar import PluginRegistrar

# The single coarse plugin-API version. A discovered plugin declares the version
# it targets via ``targets_api``; discovery fails loud on a mismatch (see
# ``PluginApiVersionMismatchError``). Bump this only on a breaking change to the
# registrar menu or the plugin contract.
#
# v2 added the optional ``add_http_error_mapper`` capability (a framework-agnostic
# transport-fault → ``ErrorReport`` mapping a host runtime renders into its own
# HTTP error response).
#
# v3 added ``add_storage_provider`` and ``add_secrets_provider`` — two config-selected,
# process-global provider registries (``storage_config.method`` / ``secrets_config.method`` pick
# the factory at boot). DX-1 batches both menu additions under this single bump so external plugins
# re-declare ``targets_api`` only once.
PLUGIN_API_VERSION: int = 3


@runtime_checkable
class PipelexPlugin(Protocol):
    """A unit of optional capability discovered at startup.

    A plugin contributes inference backends, model listers, orchestrators,
    hub-slot claims, HTTP-error mappers and teardown callbacks by calling the menu
    methods on the ``PluginRegistrar`` it is handed.

    **Invariant — a plugin belongs to exactly one layer.** Its adapters are either all kernel-layer
    (an inference backend, a storage or secrets provider) or all interpreter-layer (anything that
    constructs a `Pipe`-aware object: an orchestrator, a bundle validator, a PipeFunc executor). A
    capability that needs both is two plugins, because the built-in ones are filed by layer —
    ``pipelex.providers`` for the kernel half, ``pipelex.interpreter_plugins`` for the interpreter
    half — and a plugin straddling the two would put the method interpreter back into every kernel
    import closure. External plugins are discovered through an entry point and so live in no declared
    layer, but the same rule keeps them honest about what they pull in.

    Note that ``pipelex.providers`` is where the built-in *adapters* live, while this module and the
    rest of ``pipelex.plugins`` are the *mechanism* they register through. Both packages are
    kernel-layer; the split is about direction, not about layers — adapters depend on the mechanism
    and never the reverse. An external plugin imports ``pipelex.plugins.contract`` and
    ``pipelex.plugins.registrar``, so it is unaffected by where the built-in adapters are filed.

    **Invariant — ``register`` is side-effect-free.** It may *only* call
    registrar menu methods: no hub access, no I/O, no SDK/client construction.
    This is what makes ``build_registrar`` safe to run more than once (it runs at
    boot *and* again in the ``pipelex plugins list`` diagnostic command). Anything heavy — importing
    a backend SDK, constructing a client, importing ``temporalio`` — happens lazily
    inside the ``make_worker`` closures and the hub-slot-claim thunks, never in
    ``register`` itself.
    """

    name: str
    targets_api: int

    def register(self, registrar: "PluginRegistrar") -> None: ...
