from pydantic import BaseModel
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ImgGenPromptError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.system.runtime import ProblemReaction, runtime_manager
from pipelex.tools.misc.json_utils import json_str
from pipelex.tools.uri.uri_read_scope import UriReference


class ImgGenPrompt(BaseModel):
    positive_text: str
    negative_text: str | None = None
    input_images: list[PromptImage] | None = None

    def referenced_uris(self) -> list[UriReference]:
        """The URLs a worker will read to send this prompt: its input images given by URI."""
        return [
            UriReference(uri=image.uri, position=f"input image {index} of the image generation")
            for index, image in enumerate(self.input_images or [], start=1)
            if isinstance(image, PromptImageUri)
        ]

    def validate_before_execution(self):
        reaction = runtime_manager.problem_reactions.job
        match reaction:
            case ProblemReaction.NONE:
                pass
            case ProblemReaction.RAISE:
                if self.positive_text == "":
                    msg = "ImgGen prompt positive_text must not be an empty string"
                    raise ImgGenPromptError(msg)
            case ProblemReaction.LOG:
                if self.positive_text == "":
                    log.warning("The positive text of an image generation prompt is empty")

    @override
    def __str__(self) -> str:
        return json_str(self, title="img_gen_prompt", is_spaced=True)
