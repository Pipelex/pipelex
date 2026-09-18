"""The log-sink seam: the registrar collects per-method sink factories into a registry.

Pins the seam independent of the real built-in sinks: a factory registered for a method is the one the
registry hands back; a miss raises ``UnknownLogSinkError`` listing the registered methods; a second
registration for the same method fails loud naming both plugins; an empty registry misses every
method; and the built-in plugin contributes its three sinks under the rows ``pipelex plugins list`` shows.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from typing_extensions import override

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.exceptions import DuplicateLogSinkError, UnknownLogSinkError
from pipelex.plugins.log_sink_registry import LogSinkRegistry
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES, KERNEL_ENTRY_POINT_GROUPS
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.tools.log.log_config import LogConfig


def _fake_config() -> PipelexConfig:
    return cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=_fake_config())


class _NullLogSink(LogSink):
    @override
    def make_handler(self) -> logging.Handler:
        return logging.NullHandler()


def _fake_factory(_config: LogConfig) -> LogSink:
    """Stand-in factory: identity is all the registry tests assert (never actually invoked here)."""
    return _NullLogSink()


class TestLogSinkRegistry:
    def test_registered_factory_is_retrievable_by_method(self) -> None:
        """A factory registered for a method is the exact callable the built registry returns for it."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_log_sink(method="gcp", factory=_fake_factory)

        registry = LogSinkRegistry(registrar.log_sinks)
        assert registry.get_required(method="gcp") is _fake_factory
        assert registry.has(method="gcp")
        assert registry.methods == ["gcp"]

    def test_contribution_recorded_on_the_active_plugin(self) -> None:
        """Registering a sink records a ``log sink <method>`` contribution on the plugin's discovery."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.add_log_sink(method="gcp", factory=_fake_factory)

        assert "log sink gcp" in discovery.contributions

    def test_get_required_miss_raises_listing_registered_methods(self) -> None:
        """A miss names the requested method and lists the registered ones (the boot-time actionable error)."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_log_sink(method="json", factory=_fake_factory)
        registrar.add_log_sink(method="console", factory=_fake_factory)
        registry = LogSinkRegistry(registrar.log_sinks)

        with pytest.raises(UnknownLogSinkError) as exc_info:
            registry.get_required(method="gcp")

        assert exc_info.value.method == "gcp"
        assert set(exc_info.value.registered_methods) == {"json", "console"}
        message = str(exc_info.value)
        assert "json" in message
        assert "console" in message
        assert "runtime.log.sink" in message

    def test_empty_registry_misses_every_method(self) -> None:
        """A registry with no factories misses every method — soft via has, loud via get_required."""
        registry = LogSinkRegistry({})

        assert not registry.has(method="json")
        assert registry.methods == []
        with pytest.raises(UnknownLogSinkError):
            registry.get_required(method="json")

    def test_duplicate_method_fails_loud_naming_both_plugins(self) -> None:
        """Two plugins registering a sink for the same method is a fail-loud conflict naming both."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_log_sink(method="gcp", factory=_fake_factory)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(DuplicateLogSinkError) as exc_info:
            registrar.add_log_sink(method="gcp", factory=_fake_factory)

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert exc_info.value.method == "gcp"

    def test_the_builtin_plugin_contributes_the_three_sinks(self, mocker: MockerFixture) -> None:
        """The built-in ``log_sinks`` plugin is discovered with one contribution per shipped sink, the rows ``pipelex plugins list`` shows."""
        mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[])
        registrar = build_registrar(
            config=_fake_config(),
            boot_orchestrator=None,
            builtin_plugins=KERNEL_BUILTIN_PLUGINS,
            core_unconditional_plugin_names=KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES,
            entry_point_groups=KERNEL_ENTRY_POINT_GROUPS,
        )

        by_name = {discovery.name: discovery for discovery in registrar.discoveries}
        contributions = by_name["log_sinks"].contributions
        for method in LogSinkMethod:
            assert f"log sink {method}" in contributions
        assert set(LogSinkRegistry(registrar.log_sinks).methods) == {method.value for method in LogSinkMethod}
