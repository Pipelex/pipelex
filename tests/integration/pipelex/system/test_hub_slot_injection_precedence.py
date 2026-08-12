"""Boot-time hub-slot resolution: injection precedence (codex C8) + teardown LIFO.

At each process-global hub slot, ``Pipelex.setup`` resolves: explicit ``setup()`` param > plugin
slot-claim thunk > core default. The slot claim must never silently override an explicit injection.
Teardown runs the plugin-registered teardown callbacks LIFO. These are exercised here with a fake
registrar (no Temporal needed); the real Temporal boot-via-slots path is covered end-to-end by
``test_keyless_boot_forced_dry`` and the Temporal integration suite.
"""

from collections.abc import Generator
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from pytest_mock import MockerFixture

from pipelex.interpreter_hub import get_pipe_router
from pipelex.interpreter_plugins.pipe_func.pipe_func_plugin import PipeFuncPlugin
from pipelex.pipelex import Pipelex
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.registrar import HubSlot, PluginOrigin, PluginRegistrar
from pipelex.runtime_hub import get_content_generator
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider

if TYPE_CHECKING:
    from pipelex.system.configuration.configs import PipelexConfig


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


def _fake_registrar(mocker: MockerFixture) -> PluginRegistrar:
    """A registrar with empty registries (boot stores them but doesn't consume them during setup).

    Storage, secrets, and pipe_func are the exceptions: boot *does* select each from the registrar
    during setup. Every boot below passes an explicit ``storage_provider`` and ``secrets_provider``
    (each wins ahead of the empty registry), and the built-in ``PipeFuncPlugin`` is registered here so
    the default ``direct`` execution mode resolves — keeping this suite focused on hub slots rather
    than provider/executor selection.
    """
    registrar = PluginRegistrar(config=cast("PipelexConfig", SimpleNamespace(temporal=SimpleNamespace(is_enabled=False))))
    registrar.begin_plugin(name="pipe_func", origin=PluginOrigin.BUILTIN, targets_api=PLUGIN_API_VERSION, group=None)
    PipeFuncPlugin().register(registrar)
    mocker.patch("pipelex.runtime_boot.build_registrar", return_value=registrar)
    return registrar


class TestHubSlotInjectionPrecedence:
    def test_slot_claim_provides_content_generator_when_no_explicit_param(self, mocker: MockerFixture) -> None:
        """With no explicit param, a claimed slot's thunk result wins over the core default."""
        claimed = mocker.sentinel.claimed_content_generator
        registrar = _fake_registrar(mocker)
        registrar.slot_claims[HubSlot.CONTENT_GENERATOR] = lambda: claimed

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            storage_provider=InMemoryStorageProvider(),
            secrets_provider=EnvSecretsProvider(),
        )

        assert get_content_generator() is claimed

    def test_explicit_content_generator_wins_over_slot_claim(self, mocker: MockerFixture) -> None:
        """An explicit setup() param wins over a plugin slot claim — the claim must not override it."""
        claimed = mocker.sentinel.claimed_content_generator
        explicit = mocker.sentinel.explicit_content_generator
        registrar = _fake_registrar(mocker)
        registrar.slot_claims[HubSlot.CONTENT_GENERATOR] = lambda: claimed

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            content_generator=explicit,  # pyright: ignore[reportArgumentType]
            storage_provider=InMemoryStorageProvider(),
            secrets_provider=EnvSecretsProvider(),
        )

        assert get_content_generator() is explicit

    def test_explicit_pipe_router_wins_over_slot_claim(self, mocker: MockerFixture) -> None:
        """The explicit pipe_router param wins over a PIPE_ROUTER slot claim."""
        claimed_router = mocker.sentinel.claimed_router
        explicit_router = mocker.sentinel.explicit_router
        registrar = _fake_registrar(mocker)
        registrar.slot_claims[HubSlot.PIPE_ROUTER] = lambda: claimed_router
        # Claim PIPE_RUN too so boot does not build a default PipeRun from the sentinel router.
        registrar.slot_claims[HubSlot.PIPE_RUN] = lambda: mocker.sentinel.claimed_run

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            pipe_router=explicit_router,  # pyright: ignore[reportArgumentType]
            storage_provider=InMemoryStorageProvider(),
            secrets_provider=EnvSecretsProvider(),
        )

        assert get_pipe_router() is explicit_router

    def test_teardown_callbacks_run_lifo(self, mocker: MockerFixture) -> None:
        """Plugin-registered teardown callbacks run last-registered-first."""
        order: list[str] = []
        registrar = _fake_registrar(mocker)
        registrar.teardown_callbacks.extend(
            [
                lambda: order.append("first"),
                lambda: order.append("second"),
                lambda: order.append("third"),
            ]
        )

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            storage_provider=InMemoryStorageProvider(),
            secrets_provider=EnvSecretsProvider(),
        )
        Pipelex.teardown_if_needed()

        assert order == ["third", "second", "first"]

    def test_one_raising_teardown_callback_does_not_skip_the_others(self, mocker: MockerFixture) -> None:
        """Teardown is best-effort *per callback*, so a bad plugin cannot strand a good one's resources.

        Catching around the loop rather than inside it looks equivalent and is not: by the time an
        exception reaches the caller the loop has already exited, so every remaining callback is
        skipped — and with two plugins registered, the second one's runtime stays live. The raiser is
        registered *last* so LIFO reaches it *first*, which is the ordering that strands the others.
        """
        order: list[str] = []
        registrar = _fake_registrar(mocker)

        def _boom() -> None:
            order.append("raiser")
            msg = "plugin teardown exploded"
            raise RuntimeError(msg)

        registrar.teardown_callbacks.extend([lambda: order.append("survivor"), _boom])

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            needs_inference=False,
            storage_provider=InMemoryStorageProvider(),
            secrets_provider=EnvSecretsProvider(),
        )
        # Must not propagate: no caller of a teardown can act on "plugin B failed to release".
        Pipelex.teardown_if_needed()

        assert order == ["raiser", "survivor"], "a raising callback skipped the remaining teardown callbacks"

    def test_a_failed_interpreter_tail_still_runs_plugin_teardown_callbacks(self, mocker: MockerFixture) -> None:
        """A boot that dies after the TASK_MANAGER thunk must not leak the runtime it started.

        The thunk starts a live plugin runtime — for a Temporal worker, threads and a client
        connection — and it runs in the runtime half of the boot, so every interpreter-tail step
        happens after it. `make()` handles a failure with `_release_after_failed_boot()`, which
        releases process-global *state*; without the plugin callbacks it would leave the started
        runtime running, and nothing else on that path calls them.

        The boot split is what made this reachable in more than one place: the thunk used to run
        *after* the pipe-func executor resolution, `pipeline_manager.setup()` and the pipe-class
        registration, and now runs before all three. An injected `PipelineManager` whose `setup()`
        raises stands in for any of them.
        """
        order: list[str] = []
        registrar = _fake_registrar(mocker)
        registrar.slot_claims[HubSlot.TASK_MANAGER] = lambda: order.append("task_manager_started")
        registrar.teardown_callbacks.append(lambda: order.append("plugin_torn_down"))

        exploding_pipeline_manager = mocker.Mock()
        exploding_pipeline_manager.setup.side_effect = RuntimeError("interpreter tail failed")

        with pytest.raises(RuntimeError, match="interpreter tail failed"):
            Pipelex.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                pipeline_manager=exploding_pipeline_manager,
                storage_provider=InMemoryStorageProvider(),
                secrets_provider=EnvSecretsProvider(),
            )

        # Asserting the start too, so this cannot pass by the thunk simply never having run —
        # which would make the leak window imaginary and the test vacuous.
        assert order == ["task_manager_started", "plugin_torn_down"]
