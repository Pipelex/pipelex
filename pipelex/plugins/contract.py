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
# process-global provider registries (``runtime.storage.method`` / ``runtime.secrets.method`` pick
# the factory at boot). Both menu additions were batched under this single bump so external plugins
# re-declare ``targets_api`` only once.
#
# v4 split the single ``pipelex.plugins`` entry-point group into the two ``PluginGroup`` groups
# below: a plugin now declares its layer by the group it publishes under, and a kernel-group plugin
# may no longer reach the interpreter tier of the menu.
#
# ``add_log_sink`` — a third config-selected, process-global registry (``runtime.log.sink`` picks the
# factory at boot) — joined the menu under v4 without a bump: a menu addition breaks no plugin that
# targets v4, and a bump would have made every installed plugin re-declare ``targets_api`` for nothing.
#
# ``InferenceFamily.DOC_GEN`` — the document engines a ``PipeDocGen`` step prints with, each a model of the
# ``doc_gen`` family registered through ``add_inference_backend`` — joined under v4 on the same reasoning. What an
# engine uses in ``pipelex.cogt.doc_gen`` is part of the contract, and a breaking change to any of it is a bump: the
# worker (``DocGenWorkerAbstract``), the render job with its resources and rendered document (``render_job``), the
# formats and sources (``doc_gen_format``), ``DocGenRenderError``, the layout tree an engine writes (``layout_tree``),
# and the template check request with its findings (``template_check``) and input shapes (``InputShape`` and
# ``InputShapeKind``). Two modules joined it under v5 without a bump, since an addition breaks no plugin that targets
# v5: the rules by which every engine shows the tree's values (``layout_display``: ``display_scalar``,
# ``is_numeric_column``, ``markdown_as_html``) and the environment an engine fills a template of plain data in
# (``template_environment``).
#
# ``add_internal_model`` and ``add_doc_gen_default`` — plain data a plugin declares for the model manager to merge at
# boot: a model of the internal backend, as the table a backend file would hold, and the model deck's default engine for
# one document format and source — joined under v4 without a bump, on the same reasoning as ``add_log_sink``.
#
# v5 changed the log-sink factory contract: boot now resolves the secrets provider before the log sink, and
# a ``LogSinkFactoryFn`` receives it as the ``secrets_provider`` keyword argument, so a sink's settings can
# name a secret. A factory written against v4 would be called with a keyword it does not accept and fail at
# boot with a bare ``TypeError``; the bump turns that into a discovery-time mismatch naming the plugin.
PLUGIN_API_VERSION: int = 5


@runtime_checkable
class PipelexPlugin(Protocol):
    """A unit of optional capability discovered at startup.

    A plugin contributes inference backends, internal models and model deck defaults, model listers,
    orchestrators, hub-slot claims, HTTP-error mappers and teardown callbacks by calling the menu
    methods on the ``PluginRegistrar`` it is handed.

    **Invariant — a plugin belongs to exactly one layer, and it is the highest tier it contributes
    to.** A plugin that contributes *any* interpreter-layer capability — anything constructing a
    `Pipe`-aware object: an orchestrator, a bundle validator, a PipeFunc executor — is an
    interpreter-layer plugin and publishes under ``PluginGroup.INTERPRETER``. It may contribute
    kernel-tier capabilities alongside them, and ours does: it registers an orchestrator
    (interpreter-tier) *and* an HTTP-error mapper (kernel-tier). Do not split such a plugin in two.
    A plugin contributing only kernel-tier capabilities — an inference backend, an internal model or a
    model deck default, a model lister, a storage or secrets provider, an HTTP-error mapper — is a
    kernel-layer plugin and publishes under
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
