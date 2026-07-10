import importlib.metadata
from typing import TYPE_CHECKING, cast

from pipelex import log
from pipelex.plugins.builtins import BUILTIN_PLUGINS, CORE_UNCONDITIONAL_PLUGIN_NAMES
from pipelex.plugins.contract import PLUGIN_API_VERSION, PipelexPlugin
from pipelex.plugins.exceptions import (
    BrokenPluginError,
    CoreUnconditionalPluginDisabledError,
    PluginApiVersionMismatchError,
    PluginError,
)
from pipelex.plugins.registrar import PluginDiscovery, PluginOrigin, PluginRegistrar, PluginStatus

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig

# External plugins advertise themselves under this entry-point group:
#   [project.entry-points."pipelex.plugins"]
#   my_plugin = "my_package:make_plugin"
ENTRY_POINT_GROUP = "pipelex.plugins"


def build_registrar(*, config: "PipelexConfig") -> PluginRegistrar:
    """Discover every plugin and let each register itself into a fresh registrar.

    A **pure function**: it touches no global state and constructs no client/SDK,
    so it is safe to call more than once (D3 runs it at CLI-build to harvest
    commands and again at boot). Iterates ``BUILTIN_PLUGINS`` first, then external
    ``pipelex.plugins`` entry points; version-checks each; skips (and logs) any
    plugin named in ``config.plugins.disabled`` — externals are denylisted by their
    entry-point name *before* ``load()`` so a broken installed plugin can still be
    disabled; and is fail-loud on every conflict (duplicate backend/mode/slot,
    version mismatch, broken plugin).
    """
    registrar = PluginRegistrar(config=config)
    disabled = set(config.plugins.disabled)

    # Built-ins are already instantiated, so their name is known up front.
    for plugin in BUILTIN_PLUGINS:
        if _skip_if_disabled(registrar=registrar, name=plugin.name, origin=PluginOrigin.BUILTIN, targets_api=plugin.targets_api, disabled=disabled):
            continue
        _register_plugin(registrar=registrar, plugin=plugin, origin=PluginOrigin.BUILTIN)

    # External entry points: denylist by entry-point name *before* load(), so a
    # broken/dependency-missing installed plugin can still be recovered by disabling
    # it. A working external plugin may set a ``.name`` that differs from its
    # entry-point name; the post-load check honors the denylist on that too, so
    # either name disables it.
    for entry_point in _external_entry_points():
        if _skip_if_disabled(registrar=registrar, name=entry_point.name, origin=PluginOrigin.EXTERNAL, targets_api=None, disabled=disabled):
            continue
        plugin = _load_external_plugin(entry_point)
        if _skip_if_disabled(registrar=registrar, name=plugin.name, origin=PluginOrigin.EXTERNAL, targets_api=plugin.targets_api, disabled=disabled):
            continue
        _register_plugin(registrar=registrar, plugin=plugin, origin=PluginOrigin.EXTERNAL)

    return registrar


def _skip_if_disabled(*, registrar: PluginRegistrar, name: str, origin: PluginOrigin, targets_api: int | None, disabled: set[str]) -> bool:
    """Record and skip a denylisted plugin; return ``True`` if it was skipped.

    Fail-loud when a core-unconditional plugin is denylisted — that is a
    configuration error, never a silent no-op.
    """
    if name not in disabled:
        return False
    if name in CORE_UNCONDITIONAL_PLUGIN_NAMES:
        raise CoreUnconditionalPluginDisabledError(plugin_name=name)
    log.info(f"Plugin '{name}' is disabled via plugins.disabled; skipping.")
    registrar.discoveries.append(
        PluginDiscovery(
            name=name,
            origin=origin,
            status=PluginStatus.DISABLED,
            targets_api=targets_api,
            detail="disabled via plugins.disabled",
        )
    )
    return True


def _external_entry_points() -> list[importlib.metadata.EntryPoint]:
    return list(importlib.metadata.entry_points(group=ENTRY_POINT_GROUP))


def _load_external_plugin(entry_point: importlib.metadata.EntryPoint) -> PipelexPlugin:
    try:
        loaded = entry_point.load()
        # The entry point resolves to a plugin instance, or to a zero-arg factory
        # (a class or function) returning one.
        return cast("PipelexPlugin", loaded() if callable(loaded) else loaded)
    except Exception as exc:
        # Case 2: loading/constructing a third-party plugin from an entry point is an unbounded surface.
        raise BrokenPluginError(plugin_name=entry_point.name, reason=f"failed to load entry point: {exc}") from exc


def _register_plugin(*, registrar: PluginRegistrar, plugin: PipelexPlugin, origin: PluginOrigin) -> None:
    targets_api = getattr(plugin, "targets_api", None)
    if targets_api != PLUGIN_API_VERSION:
        raise PluginApiVersionMismatchError(
            plugin_name=getattr(plugin, "name", "<unknown>"), targets_api=targets_api, supported_api=PLUGIN_API_VERSION
        )
    registrar.begin_plugin(name=plugin.name, origin=origin, targets_api=PLUGIN_API_VERSION)
    try:
        plugin.register(registrar)
    except PluginError:
        # Our own structured, fail-loud conflicts (duplicate backend/mode/slot)
        # already name both contributors — propagate them verbatim.
        raise
    except Exception as exc:
        # Case 2: plugin.register is unbounded third-party dispatch.
        raise BrokenPluginError(plugin_name=plugin.name, reason=str(exc)) from exc
