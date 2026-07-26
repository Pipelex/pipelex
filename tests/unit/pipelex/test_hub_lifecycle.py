"""The two hubs are installed and released together.

Splitting one god-object into two singletons introduces a lifecycle risk the single hub did not
have: a boot or a teardown that touches one half and forgets the other leaves a half-reset process,
which surfaces as cross-test pollution rather than a clean failure. These tests pin both ends —
that a boot installs both singletons, and that the reset ``Pipelex.teardown`` performs really does
release the class-registry scoping the InterpreterHub installed.
"""

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel

from pipelex.interpreter_hub import (
    InterpreterHub,
    clear_current_library,
    get_current_library_id_or_none,
    get_interpreter_hub,
    get_library_manager,
    set_current_library,
    set_interpreter_hub,
)
from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import RuntimeHub, get_class_registry
from pipelex.system.registries.class_registry_access import class_registry_scoping
from pipelex.system.runtime import IntegrationMode, runtime_manager


class LifecycleScopedModel(BaseModel):
    lifecycle_field: str


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestHubLifecycle:
    def test_boot_installs_both_hub_singletons(self) -> None:
        """A booted Pipelex owns both hubs and has installed each as its process singleton."""
        pipelex = Pipelex.get_instance()

        assert RuntimeHub.get_optional_instance() is pipelex.runtime_hub
        assert InterpreterHub.get_optional_instance() is pipelex.interpreter_hub

    def test_installing_the_interpreter_hub_installs_the_class_registry_scoping(self) -> None:
        """Library scoping is live exactly because a InterpreterHub was installed (the D5 resolver)."""
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        scoped_registry = ClassRegistry()
        scoped_registry.register_class(LifecycleScopedModel)
        library.set_class_registry(scoped_registry)

        set_current_library(library_id=library_id)
        try:
            assert get_class_registry() is scoped_registry
        finally:
            clear_current_library()
            library_manager.teardown(library_id=library_id)

    def test_reset_releases_the_class_registry_scoping(self) -> None:
        """The reset primitive drops scoping, so a torn-down manager is unreachable.

        Without it, a still-pinned library_id would keep routing ``get_class_registry`` through a
        library manager whose libraries have been released. This pins ``reset()``'s own semantics;
        that ``Pipelex.teardown`` actually calls it is pinned by the last test in this class.
        """
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        scoped_registry = ClassRegistry()
        scoped_registry.register_class(LifecycleScopedModel)
        library.set_class_registry(scoped_registry)

        set_current_library(library_id=library_id)
        try:
            assert get_class_registry() is scoped_registry

            class_registry_scoping.reset()  # what Pipelex.teardown does

            assert get_class_registry() is KajsonManager.get_class_registry()
        finally:
            # Re-install the resolver exactly as a fresh boot would, so this test leaves no
            # unscoped hub behind for the rest of the worker's session.
            set_interpreter_hub(get_interpreter_hub())
            clear_current_library()
            library_manager.teardown(library_id=library_id)

        assert get_class_registry() is KajsonManager.get_class_registry()

    def test_the_real_teardown_releases_scoping_and_a_fresh_boot_reinstalls_it(self) -> None:
        """The production ``Pipelex.teardown`` path, not a stand-in for it — and the boot that follows.

        The sibling test above calls ``class_registry_scoping.reset()`` directly, which pins the
        primitive but nothing about the wiring: delete the ``reset()`` line from ``Pipelex.teardown``
        and every other test still passes, because a stale ``_library_id`` resolves to ``None`` and
        falls back to the global registry rather than raising. This test is the one that notices, and
        it also pins the other half — that a fresh boot re-installs the resolver rather than leaving
        the process permanently unscoped.

        Runs last in this class: it tears the process singleton down and rebuilds it, so it must not
        run ahead of the tests that read the booted instance.
        """
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        scoped_registry = ClassRegistry()
        scoped_registry.register_class(LifecycleScopedModel)
        library.set_class_registry(scoped_registry)
        set_current_library(library_id=library_id)
        assert get_class_registry() is scoped_registry

        Pipelex.teardown_if_needed()

        # Teardown does not clear the contextvar, so the library stays pinned — releasing the
        # resolver is the whole of what makes the torn-down library unreachable through it.
        assert get_current_library_id_or_none() == library_id
        assert get_class_registry() is KajsonManager.get_class_registry()

        clear_current_library()
        Pipelex.make(integration_mode=_test_integration_mode())

        fresh_manager = get_library_manager()
        fresh_library_id, fresh_library = fresh_manager.open_library()
        fresh_registry = ClassRegistry()
        fresh_registry.register_class(LifecycleScopedModel)
        fresh_library.set_class_registry(fresh_registry)
        set_current_library(library_id=fresh_library_id)
        try:
            assert get_class_registry() is fresh_registry
        finally:
            clear_current_library()
            fresh_manager.teardown(library_id=fresh_library_id)
