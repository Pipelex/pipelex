"""Contract-conformance tests for plugin discovery: protocol satisfaction, fail-loud
conflict/version policy, the side-effect-free (idempotent) register invariant, and the
plugins.disabled denylist.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.contract import PLUGIN_API_VERSION, PipelexPlugin
from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.exceptions import (
    BrokenPluginError,
    CoreUnconditionalPluginDisabledError,
    DuplicateInferenceBackendError,
    DuplicateOrchestratorError,
    HubSlotAlreadyClaimedError,
    PluginApiVersionMismatchError,
)
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar, PluginStatus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pytest_mock import MockerFixture

    from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
    from pipelex.plugins.orchestrator_registry import OrchestratorProtocol
    from pipelex.system.configuration.configs import PipelexConfig

DISCOVERY_MODULE = "pipelex.plugins.discovery"

#: The default for tests that exercise no core-unconditional plugin: nothing is undisableable.
NO_CORE_UNCONDITIONAL: frozenset[str] = frozenset()


def _noop_make_worker(**_kwargs: object) -> InferenceWorkerAbstract:
    msg = "make_worker is never invoked by discovery tests"
    raise AssertionError(msg)


def _fake_config(disabled: list[str]) -> PipelexConfig:
    # Discovery reads ``config.plugins.disabled`` to apply the denylist. No builtin's
    # register() reads config: Temporal — the only plugin that did, via ``temporal.is_enabled``
    # — now ships as the external pipelex-temporal dist.
    return cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=disabled)))


class _InferencePlugin:
    def __init__(self, *, name: str, sdk: str, targets_api: int = PLUGIN_API_VERSION):
        self.name = name
        self.sdk = sdk
        self.targets_api = targets_api

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_inference_backend(family=InferenceFamily.LLM, sdk=self.sdk, make_worker=_noop_make_worker)


class _OrchestratorPlugin:
    def __init__(self, *, name: str):
        self.name = name
        self.targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_orchestrator(mode="temporal", orchestrator=cast("OrchestratorProtocol", object()))


class _SlotPlugin:
    def __init__(self, *, name: str):
        self.name = name
        self.targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.claim_content_generator(object)


class _BrokenPlugin:
    name = "broken"
    targets_api = PLUGIN_API_VERSION

    def register(self, _registrar: PluginRegistrar) -> None:
        msg = "kaboom in register"
        raise ValueError(msg)


def _build_registrar_with(
    *,
    mocker: MockerFixture,
    plugins: Sequence[object],
    disabled: list[str] | None = None,
    core_unconditional: frozenset[str] = NO_CORE_UNCONDITIONAL,
) -> PluginRegistrar:
    """Build a registrar over exactly ``plugins``, with external entry points stubbed out.

    The built-in list is a *parameter* of ``build_registrar`` rather than a module global it imports:
    some built-ins adapt interpreter-layer ports, so importing them from the kernel-layer discovery
    module would put the method interpreter back into every kernel import closure. Which is why these
    tests hand the list in instead of patching a module attribute.
    """
    mocker.patch(f"{DISCOVERY_MODULE}._external_entry_points", return_value=[])
    return build_registrar(
        config=_fake_config(disabled or []),
        builtin_plugins=cast("Sequence[PipelexPlugin]", plugins),
        core_unconditional_plugin_names=core_unconditional,
    )


class TestPluginDiscovery:
    def test_builtin_plugins_satisfy_the_protocol(self) -> None:
        """Every shipped built-in is a structural PipelexPlugin; a bare object is not."""
        from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS  # noqa: PLC0415

        for plugin in BUILTIN_PLUGINS:
            assert isinstance(plugin, PipelexPlugin)
        assert not isinstance(object(), PipelexPlugin)

    def test_the_two_layer_halves_compose_into_one_list(self) -> None:
        """The composition root's list is exactly both halves, and each name appears once.

        The halves are filed by layer — `pipelex.plugins` for the kernel adapters,
        `pipelex.interpreter_plugins` for the ones that construct interpreter-layer objects — so the
        failure mode this pins is a half silently dropping out of the composition, which would present
        as a plugin quietly missing at boot rather than as an import error.
        """
        from pipelex.interpreter_plugins.builtins import (  # noqa: PLC0415
            BUILTIN_PLUGINS,
            CORE_UNCONDITIONAL_PLUGIN_NAMES,
            INTERPRETER_BUILTIN_PLUGINS,
            INTERPRETER_CORE_UNCONDITIONAL_PLUGIN_NAMES,
        )
        from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES  # noqa: PLC0415

        assert [*INTERPRETER_BUILTIN_PLUGINS, *KERNEL_BUILTIN_PLUGINS] == BUILTIN_PLUGINS
        assert CORE_UNCONDITIONAL_PLUGIN_NAMES == INTERPRETER_CORE_UNCONDITIONAL_PLUGIN_NAMES | KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES
        names = [plugin.name for plugin in BUILTIN_PLUGINS]
        assert len(names) == len(set(names))
        assert set(names) >= CORE_UNCONDITIONAL_PLUGIN_NAMES

    def test_registry_round_trip(self, mocker: MockerFixture) -> None:
        """A registered backend is retrievable by (family, sdk) and is the exact callable."""
        registrar = _build_registrar_with(mocker=mocker, plugins=[_InferencePlugin(name="synthetic", sdk="synthetic_sdk")])

        from pipelex.plugins.inference_backend_registry import InferenceBackendRegistry  # noqa: PLC0415

        registry = InferenceBackendRegistry(registrar.inference_backends)
        assert registry.lookup(family=InferenceFamily.LLM, sdk="synthetic_sdk") is _noop_make_worker

    def test_version_mismatch_fails_loud(self, mocker: MockerFixture) -> None:
        future_plugin = _InferencePlugin(name="from_the_future", sdk="future_sdk", targets_api=PLUGIN_API_VERSION + 1)
        with pytest.raises(PluginApiVersionMismatchError) as exc_info:
            _build_registrar_with(mocker=mocker, plugins=[future_plugin])
        assert "from_the_future" in str(exc_info.value)

    def test_duplicate_inference_backend_names_both(self, mocker: MockerFixture) -> None:
        with pytest.raises(DuplicateInferenceBackendError) as exc_info:
            _build_registrar_with(mocker=mocker, plugins=[_InferencePlugin(name="alpha", sdk="dup"), _InferencePlugin(name="beta", sdk="dup")])
        message = str(exc_info.value)
        assert "alpha" in message
        assert "beta" in message

    def test_duplicate_orchestrator_names_both(self, mocker: MockerFixture) -> None:
        with pytest.raises(DuplicateOrchestratorError) as exc_info:
            _build_registrar_with(mocker=mocker, plugins=[_OrchestratorPlugin(name="orch_a"), _OrchestratorPlugin(name="orch_b")])
        message = str(exc_info.value)
        assert "orch_a" in message
        assert "orch_b" in message

    def test_double_claimed_slot_names_both(self, mocker: MockerFixture) -> None:
        with pytest.raises(HubSlotAlreadyClaimedError) as exc_info:
            _build_registrar_with(mocker=mocker, plugins=[_SlotPlugin(name="claimer_1"), _SlotPlugin(name="claimer_2")])
        message = str(exc_info.value)
        assert "claimer_1" in message
        assert "claimer_2" in message

    def test_broken_plugin_register_wrapped(self, mocker: MockerFixture) -> None:
        with pytest.raises(BrokenPluginError) as exc_info:
            _build_registrar_with(mocker=mocker, plugins=[_BrokenPlugin()])
        assert "broken" in str(exc_info.value)
        assert "kaboom" in str(exc_info.value)

    def test_broken_external_entry_point_wrapped(self, mocker: MockerFixture) -> None:
        """An entry point that fails to load is wrapped in BrokenPluginError naming the entry point."""

        def _explode() -> object:
            msg = "no such module"
            raise ImportError(msg)

        bad_entry_point = SimpleNamespace(name="bad_ep", load=_explode)
        mocker.patch(f"{DISCOVERY_MODULE}._external_entry_points", return_value=[bad_entry_point])
        with pytest.raises(BrokenPluginError) as exc_info:
            build_registrar(config=_fake_config([]), builtin_plugins=[], core_unconditional_plugin_names=NO_CORE_UNCONDITIONAL)
        assert "bad_ep" in str(exc_info.value)

    def test_disabled_broken_external_entry_point_is_skipped_before_load(self, mocker: MockerFixture) -> None:
        """A broken external entry point listed in plugins.disabled is skipped by its entry-point name
        *before* load(), so the denylist can recover from a bad installed plugin instead of raising BrokenPluginError.
        """

        def _explode() -> object:
            msg = "no such module"
            raise ImportError(msg)

        bad_entry_point = SimpleNamespace(name="bad_ep", load=_explode)
        mocker.patch(f"{DISCOVERY_MODULE}._external_entry_points", return_value=[bad_entry_point])

        registrar = build_registrar(config=_fake_config(["bad_ep"]), builtin_plugins=[], core_unconditional_plugin_names=NO_CORE_UNCONDITIONAL)

        disabled_discovery = next(discovery for discovery in registrar.discoveries if discovery.name == "bad_ep")
        assert disabled_discovery.status == PluginStatus.DISABLED
        assert disabled_discovery.origin == PluginOrigin.EXTERNAL

    def test_build_registrar_is_idempotent(self, mocker: MockerFixture) -> None:
        """Two builds produce equivalent registrars — register is side-effect-free (D3)."""
        synthetic = [_InferencePlugin(name="synthetic", sdk="synthetic_sdk")]
        first = _build_registrar_with(mocker=mocker, plugins=synthetic)
        second = _build_registrar_with(mocker=mocker, plugins=synthetic)
        assert set(first.inference_backends) == set(second.inference_backends)
        assert [discovery.name for discovery in first.discoveries] == [discovery.name for discovery in second.discoveries]

    def test_disabled_plugin_is_skipped(self, mocker: MockerFixture) -> None:
        registrar = _build_registrar_with(mocker=mocker, plugins=[_InferencePlugin(name="optional", sdk="optional_sdk")], disabled=["optional"])
        assert (InferenceFamily.LLM, "optional_sdk") not in registrar.inference_backends
        disabled_discovery = next(discovery for discovery in registrar.discoveries if discovery.name == "optional")
        assert disabled_discovery.status == PluginStatus.DISABLED

    @pytest.mark.parametrize("plugin_name", ["direct", "pipe_func", "storage", "secrets", "openai"])
    def test_disabling_core_unconditional_plugin_raises(self, plugin_name: str) -> None:
        """Denylisting any plugin core requires unconditionally (pipe_func/storage/secrets included) is a startup error."""
        from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS, CORE_UNCONDITIONAL_PLUGIN_NAMES  # noqa: PLC0415

        with pytest.raises(CoreUnconditionalPluginDisabledError) as exc_info:
            build_registrar(
                config=_fake_config([plugin_name]),
                builtin_plugins=BUILTIN_PLUGINS,
                core_unconditional_plugin_names=CORE_UNCONDITIONAL_PLUGIN_NAMES,
            )
        assert plugin_name in str(exc_info.value)

    def test_discoveries_describe_builtins(self) -> None:
        """build_registrar records each built-in with origin/status/contributions for `plugins list`."""
        from pipelex.interpreter_plugins.builtins import BUILTIN_PLUGINS, CORE_UNCONDITIONAL_PLUGIN_NAMES  # noqa: PLC0415

        registrar = build_registrar(
            config=_fake_config([]),
            builtin_plugins=BUILTIN_PLUGINS,
            core_unconditional_plugin_names=CORE_UNCONDITIONAL_PLUGIN_NAMES,
        )
        by_name = {discovery.name: discovery for discovery in registrar.discoveries}
        assert "openai" in by_name
        openai_discovery = by_name["openai"]
        assert openai_discovery.origin == PluginOrigin.BUILTIN
        assert openai_discovery.status == PluginStatus.REGISTERED
        assert openai_discovery.contributions  # registered at least one inference backend
