from abc import ABC, abstractmethod


class StorageProviderAbstract(ABC):
    @abstractmethod
    def load(self, uri: str) -> bytes:
        pass

    @abstractmethod
    def store(self, data: bytes, uri: str) -> str:
        pass
