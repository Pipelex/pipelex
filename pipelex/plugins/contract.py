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
#
# v4 split the single ``pipelex.plugins`` entry-point group into the two ``PluginGroup`` groups
# below: a plugin now declares its layer by the group it publishes under, and a kernel-group plugin
# may no longer reach the interpreter tier of the menu.
PLUGIN_API_VERSION: int = 4


@runtime_checkable
class PipelexPlugin(Protocol):
    """A unit of optional capability discovered at startup.

    A plugin contributes inference backends, model listers, orchestrators,
    hub-slot claims, HTTP-error mappers and teardown callbacks by calling the menu
    methods on the ``PluginRegistrar`` it is handed.

    **Invariant — a plugin belongs to exactly one layer, and it is the highest tier it contributes
    to.** A plugin that contributes *any* interpreter-layer capability — anything constructing a
    `Pipe`-aware object: an orchestrator, a bundle validator, a PipeFunc executor — is an
    interpreter-layer plugin and publishes under ``PluginGroup.INTERPRETER``. It may contribute
    kernel-tier capabilities alongside them, and ours does: it registers an orchestrator
    (interpreter-tier) *and* an HTTP-error mapper (kernel-tier). Do not split such a plugin in two.
    A plugin contributing only kernel-tier capabilities — an inference backend, a model lister, a
    storage or secrets provider, an HTTP-error mapper — is a kernel-layer plugin and publishes under
    ``PluginGroup.KERNEL``.

    An external plugin declares its layer by the group it publishes under, and the registrar enforces
    the declaration in the one direction that matters: a kernel-group plugin registering an
    interpreter-layer capability fails loud at register time (``PluginLayerViolationError``), because
    a kernel-only boot reads the kernel group and must never end up constructing a `Pipe`-aware
    object. The reverse needs no rule — a kernel-only boot never reads the interpreter group at all.
    Publishing the same plugin under *both* groups is its own error
    (``PluginDeclaredInMultipleGroupsError``): the group is the declaration, so declaring two says
    nothing. Built-ins carry no group and are filed by layer in-tree instead — ``pipelex.providers``
    for the kernel half, ``pipelex.interpreter_plugins`` for the interpreter half — where the
    hub-layering guard polices the same boundary statically.

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
