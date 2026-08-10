"""The layer split in plugin discovery: two entry-point groups, the menu-tier cross-check that
keeps a kernel-group plugin honest, and the fail-loud probe on the retired single group.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.discovery import RETIRED_ENTRY_POINT_GROUP, build_registrar
from pipelex.plugins.exceptions import PluginLayerViolationError, RetiredPluginEntryPointGroupError
from pipelex.plugins.inference_backend_registry import InferenceFamily
from pipelex.plugins.plugin_group import PluginGroup

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from pytest_mock import MockerFixture

    from pipelex.base_exceptions import ErrorReport
    from pipelex.cogt.inference.inference_worker_abstract import InferenceWorkerAbstract
    from pipelex.plugins.bundle_validator_registry import BundleValidatorProtocol
    from pipelex.plugins.contract import PipelexPlugin
    from pipelex.plugins.orchestrator_registry import OrchestratorProtocol
    from pipelex.plugins.pipe_func_executor_registry import PipeFuncExecutorFactoryFn
    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.system.configuration.configs import PipelexConfig

#: Every menu call that contributes an interpreter-layer capability — the set a kernel-group plugin
#: may not reach. Keyed by the fragment its violation message must name, so a renamed capability
#: shows up here rather than silently weakening the cross-check.
INTERPRETER_TIER_CALLS: dict[str, Callable[[PluginRegistrar], None]] = {
    "orchestrator": lambda registrar: registrar.add_orchestrator(mode="temporal", orchestrator=cast("OrchestratorProtocol", object())),
    "bundle validator": lambda registrar: registrar.add_bundle_validator(mode="temporal", validator=cast("BundleValidatorProtocol", object())),
    "pipe_func executor": lambda registrar: registrar.add_pipe_func_executor(mode="daytona", factory=cast("PipeFuncExecutorFactoryFn", object)),
    "hub slot pipe_router": lambda registrar: registrar.claim_pipe_router(object),
    "hub slot pipe_run": lambda registrar: registrar.claim_pipe_run(object),
    "hub slot pipe_func_executor": lambda registrar: registrar.claim_pipe_func_executor(object),
}

#: The other half of `HubSlot.is_interpreter_layer` — the slots a kernel-group plugin may claim.
#: Asserted explicitly because the exhaustive match forces a *classification* on every new slot but
#: not a correct one: with only the refusals pinned, moving any of these into the interpreter arm
#: would silently narrow what a kernel-group plugin can do and no test would object.
KERNEL_TIER_CLAIMS: dict[str, Callable[[PluginRegistrar], None]] = {
    "content_generator": lambda registrar: registrar.claim_content_generator(object),
    "task_manager": lambda registrar: registrar.claim_task_manager(object),
    "isolated_execution_probe": lambda registrar: registrar.claim_isolated_execution_probe(object),
}


def _noop_make_worker(**_kwargs: object) -> InferenceWorkerAbstract:
    msg = "make_worker is never invoked by discovery tests"
    raise AssertionError(msg)


def _fake_config() -> PipelexConfig:
    return cast("PipelexConfig", SimpleNamespace(plugins=SimpleNamespace(disabled=[])))


class _ContributingPlugin:
    """A plugin whose ``register`` runs exactly the menu calls it was handed."""

    def __init__(self, *, name: str, contributions: Sequence[Callable[[PluginRegistrar], None]]):
        self.name = name
        self.targets_api = PLUGIN_API_VERSION
        self._contributions = contributions

    def register(self, registrar: PluginRegistrar) -> None:
        for contribute in self._contributions:
            contribute(registrar)


def _add_inference_backend(registrar: PluginRegistrar) -> None:
    registrar.add_inference_backend(family=InferenceFamily.LLM, sdk="synthetic_sdk", make_worker=_noop_make_worker)


def _add_http_error_mapper(registrar: PluginRegistrar) -> None:
    registrar.add_http_error_mapper(exc_type_provider=lambda: TimeoutError, to_error_report=cast("Callable[..., ErrorReport]", object))


def _entry_point(*, name: str, plugin: object) -> SimpleNamespace:
    """An entry point resolving to an already-instantiated plugin, like ``my_package:make_plugin``."""
    return SimpleNamespace(name=name, load=lambda: plugin)


def _discover(
    *,
    mocker: MockerFixture,
    external: dict[str, list[object]] | None = None,
    retired: list[object] | None = None,
    groups: Sequence[PluginGroup] = (PluginGroup.KERNEL, PluginGroup.INTERPRETER),
    builtins: Sequence[object] = (),
) -> PluginRegistrar:
    """Run discovery against a synthetic installed-distribution set, keyed by entry-point group.

    Patches ``importlib.metadata.entry_points`` rather than this module's own helper, so the
    group filtering under test is the real one — a group the caller did not ask for must never
    be read, and that is only observable if discovery does the querying itself.
    """
    by_group: dict[str, list[object]] = dict(external or {})
    by_group[RETIRED_ENTRY_POINT_GROUP] = retired or []

    def _installed(*, group: str) -> list[object]:
        return by_group.get(group, [])

    mocker.patch("importlib.metadata.entry_points", side_effect=_installed)
    return build_registrar(
        config=_fake_config(),
        builtin_plugins=cast("Sequence[PipelexPlugin]", builtins),
        core_unconditional_plugin_names=frozenset(),
        entry_point_groups=groups,
    )


class TestPluginGroupSplit:
    def test_a_kernel_group_plugin_contributes_kernel_capabilities_and_records_its_group(self, mocker: MockerFixture) -> None:
        """The kernel tier is what a kernel-group plugin is for; `plugins list` reads the group back."""
        plugin = _ContributingPlugin(name="synthetic_backend", contributions=[_add_inference_backend, _add_http_error_mapper])
        registrar = _discover(mocker=mocker, external={PluginGroup.KERNEL: [_entry_point(name="synthetic_backend", plugin=plugin)]})

        assert (InferenceFamily.LLM, "synthetic_sdk") in registrar.inference_backends
        discovery = next(discovery for discovery in registrar.discoveries if discovery.name == "synthetic_backend")
        assert discovery.group == PluginGroup.KERNEL

    @pytest.mark.parametrize("capability", list(INTERPRETER_TIER_CALLS))
    def test_a_kernel_group_plugin_reaching_the_interpreter_tier_fails_loud(self, capability: str, mocker: MockerFixture) -> None:
        """A plugin lying about its layer is caught at register time, before anything is wired."""
        plugin = _ContributingPlugin(name="liar", contributions=[INTERPRETER_TIER_CALLS[capability]])
        with pytest.raises(PluginLayerViolationError) as exc_info:
            _discover(mocker=mocker, external={PluginGroup.KERNEL: [_entry_point(name="liar", plugin=plugin)]})

        message = str(exc_info.value)
        assert "liar" in message
        assert capability in message
        assert PluginGroup.INTERPRETER in message

    @pytest.mark.parametrize("slot", list(KERNEL_TIER_CLAIMS))
    def test_a_kernel_group_plugin_may_claim_the_kernel_tier_hub_slots(self, slot: str, mocker: MockerFixture) -> None:
        """Not every hub slot is interpreter-layer, and the permission matters as much as the refusal.

        These three hand back no `Pipe`-aware object and are applied in the kernel boot, so refusing
        them would push a plugin that needs one into the interpreter group — where a kernel-only boot
        would never load it at all. That is the silent-absence failure the split exists to remove, so
        over-restricting here is not a safe direction to err in.
        """
        plugin = _ContributingPlugin(name="kernel_claimant", contributions=[KERNEL_TIER_CLAIMS[slot]])
        registrar = _discover(mocker=mocker, external={PluginGroup.KERNEL: [_entry_point(name="kernel_claimant", plugin=plugin)]})

        discovery = next(discovery for discovery in registrar.discoveries if discovery.name == "kernel_claimant")
        assert discovery.group == PluginGroup.KERNEL
        assert slot in str(discovery.contributions)

    def test_an_interpreter_group_plugin_may_contribute_both_tiers(self, mocker: MockerFixture) -> None:
        """The tiers are a *menu restriction on the kernel group*, not a partition.

        Our own Temporal plugin is the case that settles the direction: it is interpreter-side (it
        contributes an orchestrator) and it also contributes an HTTP-error mapper, a kernel-tier
        capability. A symmetric rule would reject it — and would be rejecting nothing dangerous, since
        a kernel-only boot never loads the interpreter group in the first place.
        """
        plugin = _ContributingPlugin(
            name="synthetic_orchestrator",
            contributions=[INTERPRETER_TIER_CALLS["orchestrator"], _add_http_error_mapper, _add_inference_backend],
        )
        registrar = _discover(mocker=mocker, external={PluginGroup.INTERPRETER: [_entry_point(name="synthetic_orchestrator", plugin=plugin)]})

        assert registrar.orchestrators
        assert registrar.http_error_mappers
        assert (InferenceFamily.LLM, "synthetic_sdk") in registrar.inference_backends

    def test_a_builtin_is_not_subject_to_the_cross_check(self, mocker: MockerFixture) -> None:
        """Built-ins arrive under no entry-point group — they are filed by layer in-tree instead.

        `direct` and `pipe_func` are interpreter-layer built-ins that a kernel-only boot simply never
        passes in, and the hub-layering guard already polices where they may live.
        """
        plugin = _ContributingPlugin(name="direct_like", contributions=[INTERPRETER_TIER_CALLS["orchestrator"]])
        registrar = _discover(mocker=mocker, builtins=[plugin])

        assert registrar.orchestrators
        discovery = next(discovery for discovery in registrar.discoveries if discovery.name == "direct_like")
        assert discovery.group is None

    def test_a_kernel_only_boot_never_loads_an_interpreter_group_entry_point(self, mocker: MockerFixture) -> None:
        """The whole point of the split: not loaded, not merely not registered.

        An interpreter-group plugin's module is what drags the method interpreter into the process, so
        the guarantee has to be about ``load()``, not about what ends up in the registrar.
        """
        loaded: list[str] = []

        def _exploding_load() -> object:
            loaded.append("interpreter_side")
            msg = "a kernel-only boot must not load an interpreter-group entry point"
            raise AssertionError(msg)

        interpreter_entry_point = SimpleNamespace(name="interpreter_side", load=_exploding_load)
        kernel_plugin = _ContributingPlugin(name="kernel_side", contributions=[_add_inference_backend])
        registrar = _discover(
            mocker=mocker,
            external={
                PluginGroup.KERNEL: [_entry_point(name="kernel_side", plugin=kernel_plugin)],
                PluginGroup.INTERPRETER: [interpreter_entry_point],
            },
            groups=(PluginGroup.KERNEL,),
        )

        assert not loaded
        assert [discovery.name for discovery in registrar.discoveries] == ["kernel_side"]

    def test_the_retired_group_is_a_loud_migration_error(self, mocker: MockerFixture) -> None:
        """Silent nondiscovery is the failure this probe exists to prevent.

        A plugin still advertising under `pipelex.plugins` would otherwise just never be found —
        no orchestrator, no backend, no error, and a run that quietly does the wrong thing.
        """

        def _never_loaded() -> object:
            msg = "a retired-group entry point must be reported, never loaded"
            raise AssertionError(msg)

        with pytest.raises(RetiredPluginEntryPointGroupError) as exc_info:
            _discover(mocker=mocker, retired=[SimpleNamespace(name="unmigrated_plugin", load=_never_loaded)])

        message = str(exc_info.value)
        assert "unmigrated_plugin" in message
        assert RETIRED_ENTRY_POINT_GROUP in message
        assert PluginGroup.KERNEL in message
        assert PluginGroup.INTERPRETER in message

    def test_a_group_the_caller_did_not_ask_for_is_never_even_queried(self, mocker: MockerFixture) -> None:
        """Group filtering happens at the metadata query, not by discarding loaded plugins afterwards."""
        queried: list[str] = []

        def _record(*, group: str) -> list[object]:
            queried.append(group)
            return []

        mocker.patch("importlib.metadata.entry_points", side_effect=_record)
        build_registrar(
            config=_fake_config(),
            builtin_plugins=[],
            core_unconditional_plugin_names=frozenset(),
            entry_point_groups=(PluginGroup.KERNEL,),
        )

        assert PluginGroup.INTERPRETER not in queried
        assert PluginGroup.KERNEL in queried
        assert RETIRED_ENTRY_POINT_GROUP in queried
