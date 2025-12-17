from abc import ABC, abstractmethod

from pipelex.cogt.image.generated_image import GeneratedImageRawDetails, GeneratedImageResolved


class GeneratedContentFactoryAbstract(ABC):
    @abstractmethod
    def make_generated_image(
        self,
        raw_details: GeneratedImageRawDetails,
    ) -> GeneratedImageResolved:
        pass
