"""The bundle-validator seam: the registrar collects per-mode validators into a registry.

Pins the seam independent of the real DIRECT/Temporal validators: a validator registered for
a mode is the one the registry hands back; a second registration for the same mode fails loud
naming both plugins; an empty registry reports the mode as absent.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.bundle_validator_registry import BundleValidatorRegistry
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.exceptions import DuplicateBundleValidatorError
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.runtime_bridge.orchestration_mode import DIRECT_ORCHESTRATION_MODE

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from pipelex.base_exceptions import ErrorReport
    from pipelex.pipeline.validation_report import PipelexValidationReport
    from pipelex.system.configuration.configs import PipelexConfig


class _FakeBundleValidator:
    """Stand-in validator: structurally a ``BundleValidatorProtocol`` (never invoked here)."""

    async def validate_bundles(
        self,
        *,
        mthds_contents: list[str],
        mthds_sources: list[str] | None,
        allow_signatures: bool,
        library_dirs: Sequence[Path] | None,
    ) -> PipelexValidationReport | ErrorReport:
        raise NotImplementedError


def _make_registrar() -> PluginRegistrar:
    return PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[])))))


class TestBundleValidatorRegistry:
    def test_registered_validator_is_retrievable_by_mode(self) -> None:
        """A validator registered for a mode is the exact instance the built registry returns for it."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        validator = _FakeBundleValidator()

        registrar.add_bundle_validator(mode=DIRECT_ORCHESTRATION_MODE, validator=validator)

        registry = BundleValidatorRegistry(registrar.bundle_validators)
        assert registry.get_optional(mode=DIRECT_ORCHESTRATION_MODE) is validator
        assert registry.has(mode=DIRECT_ORCHESTRATION_MODE)
        assert registry.modes == [DIRECT_ORCHESTRATION_MODE]

    def test_contribution_recorded_on_the_active_plugin(self) -> None:
        """Registering a validator records a ``bundle validator <mode>`` contribution line on the plugin's discovery."""
        registrar = _make_registrar()
        discovery = registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        registrar.add_bundle_validator(mode="temporal", validator=_FakeBundleValidator())

        assert "bundle validator temporal" in discovery.contributions

    def test_duplicate_mode_fails_loud_naming_both_plugins(self) -> None:
        """Two plugins registering a validator for the same mode is a fail-loud conflict naming both."""
        registrar = _make_registrar()
        registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
        registrar.add_bundle_validator(mode=DIRECT_ORCHESTRATION_MODE, validator=_FakeBundleValidator())
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(DuplicateBundleValidatorError) as exc_info:
            registrar.add_bundle_validator(mode=DIRECT_ORCHESTRATION_MODE, validator=_FakeBundleValidator())

        assert exc_info.value.first_plugin == "alpha"
        assert exc_info.value.second_plugin == "beta"
        assert exc_info.value.mode == DIRECT_ORCHESTRATION_MODE

    def test_empty_registry_reports_mode_absent(self) -> None:
        """A registry with no validators misses every mode (the API maps a miss to MissingBundleValidatorError)."""
        registry = BundleValidatorRegistry({})

        assert registry.get_optional(mode=DIRECT_ORCHESTRATION_MODE) is None
        assert not registry.has(mode="temporal")
        assert registry.modes == []
