"""The PipeFunc-executor seam: the registrar collects per-mode executor factories into a registry.

Pins the seam independent of the real built-in modes: a factory registered for a mode is the one the
registry hands back; a miss raises ``UnknownPipeFuncExecutionModeError`` listing the registered modes;
a second registration for the same mode fails loud naming both plugins; an empty registry misses every
mode. Also pins that the built-in ``PipeFuncPlugin`` contributes exactly ``direct`` (the one in-process
mode core owns — sandbox modes come from the out-of-tree closed plugin) and that ``direct`` resolves to
the in-process executor.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.pipe_operators.func.in_process_pipe_func_executor import InProcessPipeFuncExecutor
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import DuplicatePipeFuncExecutorError, UnknownPipeFuncExecutionModeError
from pipelex.plugins.pipe_func.pipe_func_plugin import PipeFuncPlugin
from pipelex.plugins.pipe_func_executor_registry import DIRECT_PIPE_FUNC_EXECUTION_MODE, PipeFuncExecutorRegistry
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar

if TYPE_CHECKING:
    from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutorProtocol
    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.system.configuration.pipe_func_config import PipeFuncConfig


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))


def _fake_factory(_config: PipeFuncConfig) -> PipeFuncExecutorProtocol:
    """Stand-in factory: identity is all the registry tests assert (never actually invoked here)."""
    return InProcessPipeFuncExecutor()


class TestPipeFuncExecutorRegistry:
    def test_registered_factory_is_retrievable_by_mode(self) -> None:
        """A factory registered for a mode is the exact callable the built registry returns for it."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_pipe_func_executor(mode="daytona", factory=_fake_factory)

        registry = PipeFuncExecutorRegistry(registrar.pipe_func_executors)
        assert registry.get_required(mode="daytona") is _fake_factory
        assert registry.has(mode="daytona")
        assert registry.modes == ["daytona"]

    def test_contribution_recorded_on_the_active_plugin(self) -> None:
        """Registering an executor records a ``pipe_func executor <mode>`` contribution on the plugin's discovery."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        registrar.add_pipe_func_executor(mode="daytona", factory=_fake_factory)

        assert "pipe_func executor daytona" in discovery.contributions

    def test_get_required_miss_raises_listing_registered_modes(self) -> None:
        """A miss names the requested mode and lists the registered ones (the boot-time actionable error)."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_pipe_func_executor(mode="direct", factory=_fake_factory)
        registrar.add_pipe_func_executor(mode="local_sandbox", factory=_fake_factory)
        registry = PipeFuncExecutorRegistry(registrar.pipe_func_executors)

        with pytest.raises(UnknownPipeFuncExecutionModeError) as exc_info:
            registry.get_required(mode="daytona")

        assert exc_info.value.mode == "daytona"
        assert set(exc_info.value.registered_modes) == {"direct", "local_sandbox"}
        message = str(exc_info.value)
        assert "direct" in message
        assert "local_sandbox" in message

    def test_empty_registry_misses_every_mode(self) -> None:
        """A registry with no factories misses every mode — soft via has, loud via get_required."""
        registry = PipeFuncExecutorRegistry({})

        assert not registry.has(mode="direct")
        assert registry.modes == []
        with pytest.raises(UnknownPipeFuncExecutionModeError):
            registry.get_required(mode="direct")

    def test_duplicate_mode_fails_loud_naming_both_plugins(self) -> None:
        """Two plugins registering an executor for the same mode is a fail-loud conflict naming both."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)
        registrar.add_pipe_func_executor(mode="daytona", factory=_fake_factory)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION)

        with pytest.raises(DuplicatePipeFuncExecutorError) as exc_info:
            registrar.add_pipe_func_executor(mode="daytona", factory=_fake_factory)

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert exc_info.value.mode == "daytona"

    def test_builtin_plugin_registers_only_direct(self) -> None:
        """The core PipeFuncPlugin contributes exactly ``direct`` (in-process); sandbox modes are out of tree."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="pipe_func", origin=PluginOrigin.BUILTIN, targets_api=PLUGIN_API_VERSION)
        PipeFuncPlugin().register(registrar)

        registry = PipeFuncExecutorRegistry(registrar.pipe_func_executors)
        assert registry.modes == [DIRECT_PIPE_FUNC_EXECUTION_MODE]

        pipe_func_config = cast("PipeFuncConfig", SimpleNamespace(execution_mode=DIRECT_PIPE_FUNC_EXECUTION_MODE))
        direct_executor = registry.get_required(mode=DIRECT_PIPE_FUNC_EXECUTION_MODE)(pipe_func_config)
        assert isinstance(direct_executor, InProcessPipeFuncExecutor)
