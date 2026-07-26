from abc import abstractmethod

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_provider_abstract import PipeProviderAbstract


class PipeLibraryAbstract(PipeProviderAbstract):
    """A loaded method's pipe library: resolution (inherited) plus the management half.

    `get_required_pipe` lives on :class:`PipeProviderAbstract` in `core/`, so a core module can
    depend on pipe resolution alone. Everything below is library management and stays here, high.
    """

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
