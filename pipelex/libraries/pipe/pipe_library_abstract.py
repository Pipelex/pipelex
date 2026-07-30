from abc import ABC, abstractmethod

from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


class PipeLibraryAbstract(ABC):
    """A loaded method's pipe library: pipe resolution plus the management half.

    There is deliberately no read-side `PipeProviderAbstract` in `core/` mirroring
    :class:`~pipelex.core.concepts.concept_provider_abstract.ConceptProviderAbstract`: no core module
    takes pipe resolution as a parameter. The two places that follow a pipe reference found *inside* a
    pipe graph — a condition's mapped pipes and a sequence's last step, both in
    `pipe_machinery/rendering/` — are interpreter-layer and call `interpreter_hub.get_required_pipe`
    directly. Split the read half out if and when a runtime-layer caller needs it.
    """

    @abstractmethod
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        """Resolve a pipe code, raising when it is not known."""

    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        self.teardown()
        self.setup()

    @abstractmethod
    def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None:
        pass

    @abstractmethod
    def get_pipes(self) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def get_pipes_dict(self) -> dict[str, PipeAbstract]:
        pass

    def remove_pipes_by_refs(self, pipe_refs: list[str]) -> None:
        pass

    @abstractmethod
    def pretty_list_pipes(self) -> None:
        pass

    @abstractmethod
    def add_new_pipe(self, pipe: PipeAbstract) -> None:
        pass

    @abstractmethod
    def add_pipes(self, pipes: list[PipeAbstract]) -> None:
        pass
