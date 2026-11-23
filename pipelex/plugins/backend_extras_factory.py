from abc import ABC, abstractmethod
from typing import Any

from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


class BackendExtrasFactory(ABC):
    """What a backend adds to each request, and how it wants prompt files handed over.

    `is_storage_uri_enabled` is for a backend whose service reads Pipelex storage itself: on, a prompt
    image or document stored as a `pipelex-storage://` URI is sent as that URI, as a URL part, and the
    runtime never reads the object. It is off for every backend Pipelex ships, which receive the bytes
    as base64; a plugin backend turns it on when it builds its factory.
    """

    # Declared on the class too, so a subclass whose own `__init__` does not call this one still reads it as off.
    is_storage_uri_enabled: bool = False

    def __init__(self, *, is_storage_uri_enabled: bool = False):
        self.is_storage_uri_enabled = is_storage_uri_enabled

    @abstractmethod
    def make_extras(
        self, inference_model: InferenceModelSpec, *, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        pass
