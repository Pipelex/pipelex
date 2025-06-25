from abc import ABC, abstractmethod

LATEST_SECRET_VERSION_NAME = "latest"


class StorageProviderAbstract(ABC):
    @abstractmethod
    def get_object(self, bucket_name: str, object_key: str) -> bytes:
        pass
