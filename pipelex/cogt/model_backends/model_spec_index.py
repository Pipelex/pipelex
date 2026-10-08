"""The model specs a backend declares, or the deck serves, keyed by model type and then by handle.

A served model is identified by its model type and its handle together: one handle names one model
per model type, so `gpt-6-luna` may be an LLM and a judgment model at once, and a `PipeLLM` and a
`PipeJudge` naming it each reach their own spec. Type comes first because every lookup already
carries one, the pipe's family having fixed it; "which types serve this handle" is the rare question.
"""

from collections.abc import Iterable
from typing import Self

from pydantic import Field, RootModel

from pipelex.cogt.exceptions import InferenceModelSpecError
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.tools.typing.pydantic_utils import empty_dict_factory_of

ModelSpecsByTypeAndHandle = dict[ModelType, dict[str, InferenceModelSpec]]


class ModelSpecIndex(RootModel[ModelSpecsByTypeAndHandle]):
    """Model specs keyed by model type, then by handle, the handle being the spec's `name`.

    Both keys are read off the spec itself, so a key can never disagree with the spec it holds. The
    methods are the questions the readers ask, and the length is the number of specs, not of handles.
    """

    root: ModelSpecsByTypeAndHandle = Field(default_factory=empty_dict_factory_of(ModelType))

    @classmethod
    def make_empty(cls) -> Self:
        return cls(root={})

    @classmethod
    def make_from_specs(cls, *, model_specs: Iterable[InferenceModelSpec]) -> Self:
        """An index of these specs.

        Raises:
            InferenceModelSpecError: Two of the specs share a model type and a handle.
        """
        index = cls.make_empty()
        for model_spec in model_specs:
            index.add(model_spec)
        return index

    def add(self, model_spec: InferenceModelSpec) -> None:
        """Add a spec under its model type and its handle.

        Raises:
            InferenceModelSpecError: A spec of the same model type and handle is already here.
        """
        specs_of_type = self.root.setdefault(model_spec.model_type, {})
        if existing_spec := specs_of_type.get(model_spec.name):
            msg = (
                f"Model '{model_spec.name}' is declared twice as {model_spec.model_type.indefinite_description}, "
                f"by backend '{existing_spec.backend_name}' and by backend '{model_spec.backend_name}': "
                f"a handle names one model per model type."
            )
            raise InferenceModelSpecError(msg, backend_name=model_spec.backend_name)
        specs_of_type[model_spec.name] = model_spec

    def get(self, *, model_type: ModelType, handle: str) -> InferenceModelSpec | None:
        """The spec serving `handle` as `model_type`, or `None`."""
        return self.root.get(model_type, {}).get(handle)

    def handles_of_type(self, *, model_type: ModelType) -> list[str]:
        """Every handle served as `model_type`, sorted."""
        return sorted(self.root.get(model_type, {}))

    def all_specs(self) -> list[InferenceModelSpec]:
        """Every spec, of every model type."""
        return [model_spec for specs_of_type in self.root.values() for model_spec in specs_of_type.values()]

    def all_handles(self) -> list[str]:
        """Every handle served as some model type, each once, sorted."""
        return sorted({handle for specs_of_type in self.root.values() for handle in specs_of_type})

    def types_serving(self, *, handle: str) -> list[ModelType]:
        """The model types `handle` is served as, in the order of `ModelType`."""
        return [model_type for model_type in ModelType if handle in self.root.get(model_type, {})]

    def __len__(self) -> int:
        return sum(len(specs_of_type) for specs_of_type in self.root.values())
