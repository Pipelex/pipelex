import importlib.metadata
from typing import TYPE_CHECKING, NamedTuple, cast

from pipelex import log
from pipelex.plugins.contract import PLUGIN_API_VERSION, PipelexPlugin
from pipelex.plugins.exceptions import (
    BrokenPluginError,
    CoreUnconditionalPluginDisabledError,
    PluginApiVersionMismatchError,
    PluginError,
    RetiredPluginEntryPointGroupError,
)
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.plugins.registrar import PluginDiscovery, PluginOrigin, PluginRegistrar, PluginStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pipelex.system.configuration.configs import PipelexConfig

# External plugins advertise themselves under one of the two ``PluginGroup`` groups, which is how
# they declare their layer:
#   [project.entry-points."pipelex.plugins.kernel"]
#   my_plugin = "my_package:make_plugin"
#
# The single group they all used before the layer split. Nothing reads it any more, so a plugin left
# behind there would silently never be discovered — probed below, and fail-loud.
RETIRED_ENTRY_POINT_GROUP = "pipelex.plugins"


class GroupedEntryPoint(NamedTuple):
    """One installed entry point together with the group it was found under.

    A ``NamedTuple`` because it holds an ``EntryPoint`` (a non-pydantic third-party type) and is
    never serialized. The pairing is what lets the registrar attribute a layer to the plugin.
    """

    group: PluginGroup
    entry_point: importlib.metadata.EntryPoint


def build_registrar(
    *,
    config: "PipelexConfig",
    builtin_plugins: "Sequence[PipelexPlugin]",
    core_unconditional_plugin_names: frozenset[str],
    entry_point_groups: "Sequence[PluginGroup]",
) -> PluginRegistrar:
    """Discover every plugin and let each register itself into a fresh registrar.

    A **pure function**: it touches no global state and constructs no client/SDK,
    so it is safe to call more than once (it runs at boot and again in the
    ``pipelex plugins list`` diagnostic command). Iterates ``builtin_plugins`` first, then the
    external entry points published under ``entry_point_groups``; version-checks each; skips (and
    logs) any plugin named in ``config.plugins.disabled`` — externals are denylisted by their
    entry-point name *before* ``load()`` so a broken installed plugin can still be
    disabled; and is fail-loud on every conflict (duplicate backend/mode/slot,
    version mismatch, broken plugin, a kernel-group plugin reaching the interpreter tier).

    Args:
        config: The fully-resolved config; supplies the ``plugins.disabled`` denylist and is handed
            to the registrar for the plugins that read it.
        builtin_plugins: The built-ins to discover, in order. Injected rather than imported: some
            built-ins adapt interpreter-layer ports, and this module is kernel-layer, so importing
            the list here would put the method interpreter back into every kernel closure. The
            composed list lives in ``pipelex.interpreter_plugins.builtins`` — the layer allowed to
            weld the two halves.
        core_unconditional_plugin_names: The built-in names that may not be denylisted. Injected for
            the same reason and from the same module, so the constant never splits away from the
            plugins it describes.
        entry_point_groups: The groups to read installed plugins from — the kernel group alone for a
            kernel-only boot, both for the interpreter boot. Injected for the same reason as the two
            above: naming which groups compose a full boot is a layer decision, and this module is
            kernel-layer. A group left out is never queried, so its plugins' modules are never
            imported — which is what a kernel-only trust-base claim actually rests on.
    """
    _reject_retired_entry_point_group()
    registrar = PluginRegistrar(config=config)
    disabled = set(config.plugins.disabled)

    # Built-ins are already instantiated, so their name is known up front. They carry no group: they
    # are filed by layer in-tree, and the caller passes only the halves its layer may run.
    for plugin in builtin_plugins:
        if _skip_if_disabled(
            registrar=registrar,
            name=plugin.name,
            origin=PluginOrigin.BUILTIN,
            targets_api=plugin.targets_api,
            group=None,
            disabled=disabled,
            core_unconditional_plugin_names=core_unconditional_plugin_names,
        ):
            continue
        _register_plugin(registrar=registrar, plugin=plugin, origin=PluginOrigin.BUILTIN, group=None)

    # External entry points: denylist by entry-point name *before* load(), so a
    # broken/dependency-missing installed plugin can still be recovered by disabling
    # it. A working external plugin may set a ``.name`` that differs from its
    # entry-point name; the post-load check honors the denylist on that too, so
    # either name disables it.
    for group, entry_point in _external_entry_points(groups=entry_point_groups):
        if _skip_if_disabled(
            registrar=registrar,
            name=entry_point.name,
            origin=PluginOrigin.EXTERNAL,
            targets_api=None,
            group=group,
            disabled=disabled,
            core_unconditional_plugin_names=core_unconditional_plugin_names,
        ):
            continue
        plugin = _load_external_plugin(entry_point)
        if _skip_if_disabled(
            registrar=registrar,
            name=plugin.name,
            origin=PluginOrigin.EXTERNAL,
            targets_api=plugin.targets_api,
            group=group,
            disabled=disabled,
            core_unconditional_plugin_names=core_unconditional_plugin_names,
        ):
            continue
        _register_plugin(registrar=registrar, plugin=plugin, origin=PluginOrigin.EXTERNAL, group=group)

    return registrar


def _skip_if_disabled(
    *,
    registrar: PluginRegistrar,
    name: str,
    origin: PluginOrigin,
    targets_api: int | None,
    group: PluginGroup | None,
    disabled: set[str],
    core_unconditional_plugin_names: frozenset[str],
) -> bool:
    """Record and skip a denylisted plugin; return ``True`` if it was skipped.

    Fail-loud when a core-unconditional plugin is denylisted — that is a
    configuration error, never a silent no-op.
    """
    if name not in disabled:
        return False
    if name in core_unconditional_plugin_names:
        raise CoreUnconditionalPluginDisabledError(plugin_name=name)
    log.info(f"Plugin '{name}' is disabled via plugins.disabled; skipping.")
    registrar.discoveries.append(
        PluginDiscovery(
            name=name,
            origin=origin,
            status=PluginStatus.DISABLED,
            targets_api=targets_api,
            group=group,
            detail="disabled via plugins.disabled",
        )
    )
    return True


def _external_entry_points(*, groups: "Sequence[PluginGroup]") -> list[GroupedEntryPoint]:
    """Every installed entry point in the requested groups, paired with the group it came from.

    A group not requested is not queried, so nothing published under it is even named here — the
    ``load()`` that would import an interpreter-layer module can never be reached from a kernel-only
    boot.
    """
    return [
        GroupedEntryPoint(group=group, entry_point=entry_point) for group in groups for entry_point in importlib.metadata.entry_points(group=group)
    ]


def _reject_retired_entry_point_group() -> None:
    """Fail loud on any plugin still published under the pre-split single group.

    Probed on every build, whichever groups the caller asked for: a plugin left behind is broken in
    both boots, and the symptom without this — a capability that is simply absent, with no error —
    is the expensive one to diagnose.
    """
    stragglers = [entry_point.name for entry_point in importlib.metadata.entry_points(group=RETIRED_ENTRY_POINT_GROUP)]
    if stragglers:
        raise RetiredPluginEntryPointGroupError(
            plugin_names=stragglers,
            retired_group=RETIRED_ENTRY_POINT_GROUP,
            groups=[group.value for group in PluginGroup],
        )


def _load_external_plugin(entry_point: importlib.metadata.EntryPoint) -> PipelexPlugin:
    try:
        loaded = entry_point.load()
        # The entry point resolves to a plugin instance, or to a zero-arg factory
        # (a class or function) returning one.
        return cast("PipelexPlugin", loaded() if callable(loaded) else loaded)
    except Exception as exc:
        # Case 2: loading/constructing a third-party plugin from an entry point is an unbounded surface.
        raise BrokenPluginError(plugin_name=entry_point.name, reason=f"failed to load entry point: {exc}") from exc


def _register_plugin(*, registrar: PluginRegistrar, plugin: PipelexPlugin, origin: PluginOrigin, group: PluginGroup | None) -> None:
    targets_api = getattr(plugin, "targets_api", None)
    if targets_api != PLUGIN_API_VERSION:
        raise PluginApiVersionMismatchError(
            plugin_name=getattr(plugin, "name", "<unknown>"), targets_api=targets_api, supported_api=PLUGIN_API_VERSION
        )
    registrar.begin_plugin(name=plugin.name, origin=origin, targets_api=PLUGIN_API_VERSION, group=group)
    try:
        plugin.register(registrar)
    except PluginError:
        # Our own structured, fail-loud conflicts (duplicate backend/mode/slot)
        # already name both contributors — propagate them verbatim.
        raise
    except Exception as exc:
        # Case 2: plugin.register is unbounded third-party dispatch.
        raise BrokenPluginError(plugin_name=plugin.name, reason=str(exc)) from exc
