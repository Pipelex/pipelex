"""The two hubs are installed and released together.

Splitting one god-object into two singletons introduces a lifecycle risk the single hub did not
have: a boot or a teardown that touches one half and forgets the other leaves a half-reset process,
which surfaces as cross-test pollution rather than a clean failure. These tests pin both ends —
that a boot installs both singletons, and that the reset ``Pipelex.teardown`` performs really does
release the class-registry scoping the MethodHub installed.
"""

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel

from pipelex.method_hub import (
    MethodHub,
    clear_current_library,
    get_library_manager,
    get_method_hub,
    set_current_library,
    set_method_hub,
)
from pipelex.pipelex import Pipelex
from pipelex.service_hub import ServiceHub, get_class_registry
from pipelex.system.registries.class_registry_access import class_registry_scoping


class LifecycleScopedModel(BaseModel):
    lifecycle_field: str


class TestHubLifecycle:
    def test_boot_installs_both_hub_singletons(self) -> None:
        """A booted Pipelex owns both hubs and has installed each as its process singleton."""
        pipelex = Pipelex.get_instance()

        assert ServiceHub.get_optional_instance() is pipelex.service_hub
        assert MethodHub.get_optional_instance() is pipelex.method_hub

    def test_installing_the_method_hub_installs_the_class_registry_scoping(self) -> None:
        """Library scoping is live exactly because a MethodHub was installed (the D5 resolver)."""
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
        """The reset teardown performs drops scoping, so a torn-down manager is unreachable.

        Without it, a still-pinned library_id would keep routing ``get_class_registry`` through a
        library manager whose libraries have been released.
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
            set_method_hub(get_method_hub())
            clear_current_library()
            library_manager.teardown(library_id=library_id)

        assert get_class_registry() is KajsonManager.get_class_registry()
