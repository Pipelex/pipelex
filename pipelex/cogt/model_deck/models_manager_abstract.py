from abc import ABC, abstractmethod


class ModelsManagerAbstract(ABC):
    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def setup(self) -> None:
        pass
