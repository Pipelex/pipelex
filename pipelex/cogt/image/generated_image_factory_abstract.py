from abc import ABC, abstractmethod

from pipelex.cogt.image.generated_image import GeneratedImage


class GeneratedImageFactoryAbstract(ABC):
    @abstractmethod
    def make_generated_image(
        self,
        url: str | None = None,
        width: int | None = None,
        height: int | None = None,
        base_64_str: str | None = None,
        content_type: str | None = None,
    ) -> GeneratedImage:
        pass
