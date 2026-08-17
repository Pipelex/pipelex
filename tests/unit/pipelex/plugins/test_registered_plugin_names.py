"""The ``PluginRegistrar.registered_plugin_names`` accessor — the namespace the
``boot_orchestrator`` gate validates against. Only ``REGISTERED`` discoveries count;
``DISABLED`` / ``BROKEN`` ones never ran ``register`` and so could never claim a hub slot, making
them invalid boot-orchestrator targets.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from pipelex.plugins.registrar import PluginDiscovery, PluginOrigin, PluginRegistrar, PluginStatus

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


def _registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


class TestRegisteredPluginNames:
    def test_only_registered_discoveries_are_named(self) -> None:
        registrar = _registrar()
        registrar.discoveries.extend(
            [
                PluginDiscovery(name="temporal", origin=PluginOrigin.EXTERNAL, status=PluginStatus.REGISTERED),
                PluginDiscovery(name="optional", origin=PluginOrigin.EXTERNAL, status=PluginStatus.DISABLED),
                PluginDiscovery(name="bad_ep", origin=PluginOrigin.EXTERNAL, status=PluginStatus.BROKEN),
            ]
        )

        assert registrar.registered_plugin_names == {"temporal"}

    def test_empty_when_nothing_registered(self) -> None:
        assert _registrar().registered_plugin_names == set()
