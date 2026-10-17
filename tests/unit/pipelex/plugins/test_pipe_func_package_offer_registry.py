from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import DuplicatePipeFuncPackageOfferError
from pipelex.plugins.pipe_func_package_offer_registry import (
    PipeFuncPackageOffer,
    PipeFuncPackageOfferRegistry,
    PipeFuncPackageOfferRequest,
    PipeFuncPackageRefusal,
)
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig

_OFFER = PipeFuncPackageOffer(
    environment="the Daytona sandbox snapshot 'pipelex-base-test'",
    distributions={"pandas": "2.2.3"},
    marker_environment={"python_version": "3.12"},
)


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


def _offer_factory(_request: PipeFuncPackageOfferRequest) -> PipeFuncPackageOffer | PipeFuncPackageRefusal | None:
    return _OFFER


class TestPipeFuncPackageOfferRegistry:
    def test_an_offer_registered_for_a_mode_is_found_by_that_mode_alone(self) -> None:
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="daytona", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.add_pipe_func_package_offer(mode="daytona", factory=_offer_factory)

        registry = PipeFuncPackageOfferRegistry(registrar.pipe_func_package_offers)
        assert registry.get_optional(mode="daytona") is _offer_factory
        assert registry.get_optional(mode="direct") is None
        assert registry.modes == ["daytona"]
        assert "pipe_func package offer daytona" in discovery.contributions

    def test_two_plugins_stating_one_mode_fail_loud_naming_both(self) -> None:
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_pipe_func_package_offer(mode="daytona", factory=_offer_factory)
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(DuplicatePipeFuncPackageOfferError) as exc_info:
            registrar.add_pipe_func_package_offer(mode="daytona", factory=_offer_factory)

        assert (exc_info.value.mode, exc_info.value.first_plugin, exc_info.value.second_plugin) == ("daytona", "alpha", "beta")
        assert "'alpha'" in exc_info.value.message
        assert "'beta'" in exc_info.value.message

    def test_an_offer_refuses_a_field_it_does_not_define(self) -> None:
        """A plugin's statement is closed plain data, so a misspelled field fails at the plugin rather than reading as unstated."""
        with pytest.raises(ValueError, match="extra"):
            PipeFuncPackageOffer.model_validate({**_OFFER.model_dump(), "marker_environments": {}})

    def test_a_refusal_states_where_and_why_and_nothing_else(self) -> None:
        refusal = PipeFuncPackageRefusal(environment="the Daytona sandbox", reason="no wheel of odfpy for the box")

        assert refusal.model_dump() == {"environment": "the Daytona sandbox", "reason": "no wheel of odfpy for the box"}
        with pytest.raises(ValueError, match="extra"):
            PipeFuncPackageRefusal.model_validate({**refusal.model_dump(), "requirements": ["odfpy"]})
