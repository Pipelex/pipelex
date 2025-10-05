from abc import ABC, abstractmethod

from pipelex.core.pipes.pipe_abstract import PipeAbstract


class PipeLibraryAbstract(ABC):
    @abstractmethod
    def validate_with_libraries(self) -> None:
        pass

    @abstractmethod
    def get_required_pipe(self, pipe_code: str) -> PipeAbstract:
        pass

    @abstractmethod
    def get_optional_pipe(self, pipe_code: str) -> PipeAbstract | None:
        pass

    @abstractmethod
    def get_pipes(self) -> list[PipeAbstract]:
        pass

    @abstractmethod
    def get_pipes_dict(self) -> dict[str, PipeAbstract]:
        pass

    def remove_pipes_by_codes(self, pipe_codes: list[str]) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
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
