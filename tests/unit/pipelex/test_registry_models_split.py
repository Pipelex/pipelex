# Splitting the boot manifest in two lost nothing, and both halves still reach the class registry.
#
# `CoreRegistryModels` used to carry core's value model *and* every pipe kind. The pipe half now lives
# in `pipelex.pipe_machinery.registry_models.PipeRegistryModels`, and `pipelex.py` registers the two
# side by side. Every way of getting that wrong is silent: drop one of the two `register_classes`
# calls, or let a pipe kind and its factory drift apart, and boot still succeeds — the failure
# surfaces later as a kajson lookup miss on a pipe, in production.
#
# Nothing else in the suite covers this. The hub-lifecycle tests assert hub singletons and scoping,
# and the class-registry tests use a synthetic model, so a pipe class never being registered would
# pass them all.
#
# Every assertion below is derived from the manifests themselves — this module holds no inventory of
# what is registered, so adding a pipe kind or a content class never touches it.

from pydantic import BaseModel

from pipelex.core.registry_models import CoreRegistryModels
from pipelex.pipe_machinery.registry_models import PipeRegistryModels
from pipelex.runtime_hub import get_class_registry


def _registered_models() -> list[type[BaseModel]]:
    """Both manifests, read straight from the source rather than from whatever boot happened to register."""
    return CoreRegistryModels.get_all_models() + PipeRegistryModels.get_all_models()


def _model_names(models: list[type[BaseModel]]) -> set[str]:
    return {model.__name__ for model in models}


class TestRegistryModelsSplit:
    def test_every_pipe_kind_declares_the_factory_that_gets_looked_up_for_it(self) -> None:
        """A pipe kind and its factory never drift apart — one dropped without the other is a run-time miss.

        `PipeFactory` resolves a pipe's factory by string (`f"{pipe_type.value}Factory"`, see
        `pipelex/pipe_machinery/pipe_factory.py:121`), so this suffix pairing is the live lookup contract,
        not a naming preference. Dropping both halves is a deliberate removal and stays green.
        """
        pipe_names = _model_names(PipeRegistryModels.get_all_models())
        kinds = {name for name in pipe_names if not name.endswith("Factory")}
        factories = {name for name in pipe_names if name.endswith("Factory")}

        assert {f"{kind}Factory" for kind in kinds} == factories

    def test_no_two_registered_models_share_a_class_name(self) -> None:
        """The registry is keyed by class name, so a collision silently drops one of the two.

        kajson's `register_classes` skips a name it already holds, which makes a cross-manifest
        duplicate a debug-level no-op at boot and the wrong type at deserialization time.
        """
        models = _registered_models()

        assert len(_model_names(models)) == len(models), f"two registered models share a class name: {sorted(_model_names(models))}"

    def test_every_registered_model_is_live_in_the_booted_class_registry(self) -> None:
        """Both `register_classes` calls ran — the failure the two tests above cannot see.

        Deleting either line from `Pipelex.make` leaves a clean boot and a half-populated registry;
        kajson then fails to resolve whichever half went missing, at run time. The expectation is read
        from the manifests, not from the registry, so a deleted call cannot make this pass vacuously.
        """
        class_registry = get_class_registry()

        missing = sorted(name for name in _model_names(_registered_models()) if not class_registry.has_class(name))

        assert missing == [], f"booted class registry is missing {len(missing)} registered model(s): {missing}"
