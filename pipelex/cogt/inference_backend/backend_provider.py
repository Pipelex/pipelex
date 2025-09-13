from abc import ABC, abstractmethod


class InferenceBackendProviderAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass

    @abstractmethod
    def load_backends(self) -> None:
        pass
