"""Splitting the boot manifest in two lost nothing, and both halves still reach the class registry.

`CoreRegistryModels` used to carry core's value model *and* every pipe kind. The pipe half now lives
in `pipelex.pipe_machinery.registry_models.PipeRegistryModels`, and `pipelex.py` registers the two
side by side. That split is hand-written, and every way of getting it wrong is silent: drop a list,
drop one model out of a list, or drop one of the two `register_classes` calls, and boot still
succeeds — the failure surfaces later as a kajson deserialization error on a pipe, in production.

Nothing else in the suite covers this. The hub-lifecycle tests assert hub singletons and scoping, and
the class-registry tests use a synthetic model, so a pipe class never being registered would pass
them all. Hence three assertions here, deliberately not sampled:

- the **union** of the two manifests is exactly the frozen pre-split set, which pins every model
  rather than a representative one;
- the two are **disjoint**, so nothing is registered twice and nothing was copied instead of moved;
- every model in the union is **live in the booted class registry**, which is the only one of the
  three that notices a missing `register_classes` line.
"""

from pydantic import BaseModel

from pipelex.core.registry_models import CoreRegistryModels
from pipelex.pipe_machinery.registry_models import PipeRegistryModels
from pipelex.runtime_hub import get_class_registry

#: `CoreRegistryModels.get_all_models()` as it stood before the pipe half moved out, by class name.
#: The union of the two manifests must still equal this exactly — that is what makes the split
#: verifiable rather than merely plausible. Adding a pipe kind or a stuff-content class is a
#: deliberate change to this set; losing one is the bug this test exists to catch.
PRE_SPLIT_REGISTERED_MODEL_NAMES = frozenset(
    {
        "CompositeContent",
        "DateContent",
        "DocumentContent",
        "DynamicContent",
        "HtmlContent",
        "ImageContent",
        "JSONContent",
        "ListContent",
        "NumberContent",
        "PageContent",
        "PipeBatch",
        "PipeBatchFactory",
        "PipeCompose",
        "PipeComposeFactory",
        "PipeCondition",
        "PipeConditionFactory",
        "PipeExtract",
        "PipeExtractFactory",
        "PipeFunc",
        "PipeFuncFactory",
        "PipeImgGen",
        "PipeImgGenFactory",
        "PipeLLM",
        "PipeLLMFactory",
        "PipeParallel",
        "PipeParallelFactory",
        "PipeSearch",
        "PipeSearchFactory",
        "PipeSequence",
        "PipeSequenceFactory",
        "PipeSignature",
        "PipeSignatureFactory",
        "PipeStructure",
        "PipeStructureFactory",
        "SearchResultContent",
        "StructuredContent",
        "Stuff",
        "StuffContent",
        "TextAndImagesContent",
        "TextContent",
        "TimeContent",
        "YesNoContent",
    }
)


def _model_names(models: list[type[BaseModel]]) -> set[str]:
    return {model.__name__ for model in models}


class TestRegistryModelsSplit:
    def test_the_two_manifests_together_hold_exactly_what_the_single_one_held(self) -> None:
        """No model was dropped, renamed away or invented while hand-splitting the manifest."""
        core_models = CoreRegistryModels.get_all_models()
        pipe_models = PipeRegistryModels.get_all_models()
        union = core_models + pipe_models
        union_names = _model_names(union)

        # A name collision across the two manifests would make the set comparison below lie.
        assert len(union_names) == len(union), f"two registered models share a class name: {union_names}"
        assert union_names == PRE_SPLIT_REGISTERED_MODEL_NAMES

    def test_the_two_manifests_are_disjoint(self) -> None:
        """Nothing was copied instead of moved, so no model is registered twice."""
        core_names = _model_names(CoreRegistryModels.get_all_models())
        pipe_names = _model_names(PipeRegistryModels.get_all_models())

        assert core_names & pipe_names == set()
        # And each half holds what its name claims: core the value model, pipe_machinery the pipes.
        assert "TextContent" in core_names
        assert not any(name.startswith("Pipe") for name in core_names)
        assert "PipeLLM" in pipe_names
        assert all(name.startswith("Pipe") for name in pipe_names)

    def test_every_registered_model_is_live_in_the_booted_class_registry(self) -> None:
        """Both `register_classes` calls ran — the one failure the two tests above cannot see.

        Deleting either line from `Pipelex.make` leaves a clean boot and a half-populated registry;
        kajson then fails to deserialize whichever half went missing, at run time.
        """
        class_registry = get_class_registry()

        missing = sorted(name for name in PRE_SPLIT_REGISTERED_MODEL_NAMES if not class_registry.has_class(name))

        assert missing == [], f"booted class registry is missing {len(missing)} registered model(s): {missing}"
