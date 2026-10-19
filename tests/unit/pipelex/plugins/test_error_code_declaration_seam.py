"""A plugin declares the public codes it raises at registration; the registrar binds each to the registry, refusing an unregistered one."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import PluginErrorCodeNotRegisteredError
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


class TestErrorCodeDeclarationSeam:
    def test_declared_codes_are_bound_to_the_registry_and_attributed(self) -> None:
        """A core code and a Pipelex code, given as strings, are bound to their registry constants under the plugin's name."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.declare_error_codes(codes=["model.unavailable", "pipelex.docgen.content_unprintable"])

        assert registrar.declared_error_codes == {"alpha": (CoreCode.MODEL_UNAVAILABLE, PipelexErrorCode.DOCGEN_CONTENT_UNPRINTABLE)}
        assert discovery.contributions == ["error codes model.unavailable, pipelex.docgen.content_unprintable"]

    def test_a_plugin_declaring_twice_accumulates_its_codes_once_each(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.declare_error_codes(codes=[CoreCode.PROVIDER_FAILED])
        registrar.declare_error_codes(codes=["provider.failed", "provider.timeout"])

        assert registrar.declared_error_codes == {"alpha": (CoreCode.PROVIDER_FAILED, CoreCode.PROVIDER_TIMEOUT)}

    def test_two_plugins_may_declare_the_same_code(self) -> None:
        """A public code means one thing whoever raises it, so declaring it is no claim another plugin collides with."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.declare_error_codes(codes=["runtime.unexpected"])
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=PluginGroup.KERNEL)
        registrar.declare_error_codes(codes=["runtime.unexpected"])

        assert registrar.declared_error_codes == {"alpha": (CoreCode.RUNTIME_UNEXPECTED,), "beta": (CoreCode.RUNTIME_UNEXPECTED,)}

    @pytest.mark.parametrize(
        "unregistered_code",
        [
            "pig-07",
            "model.unknwon",
            "pipelex.manifold.body_too_large",
            "",
        ],
    )
    def test_an_unregistered_code_refuses_the_boot_as_a_broken_plugin(self, unregistered_code: str) -> None:
        """The refusal names the plugin and the code, carries `pipelex.plugin.broken`, and binds none of the plugin's codes."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(PluginErrorCodeNotRegisteredError) as exc_info:
            registrar.declare_error_codes(codes=["model.unavailable", unregistered_code])

        refusal = exc_info.value
        assert refusal.plugin_name == "alpha"
        assert refusal.code == unregistered_code
        assert refusal.resolve_error_code() == PipelexErrorCode.PLUGIN_BROKEN
        assert f"'{unregistered_code}'" in refusal.message
        assert "alpha" in refusal.message
        assert not registrar.declared_error_codes
        assert not discovery.contributions

    def test_an_empty_declaration_records_nothing(self) -> None:
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.declare_error_codes(codes=[])

        assert not registrar.declared_error_codes
        assert not discovery.contributions
