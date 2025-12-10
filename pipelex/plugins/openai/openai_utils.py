from openai.types.chat.chat_completion_content_part_image_param import ImageURL

from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImageDetail, PromptImagePath, PromptImageUrl
from pipelex.tools.misc.base_64_utils import load_binary_as_base64


async def make_image_url_obj(prompt_image: PromptImage, detail: PromptImageDetail | None) -> ImageURL:
    if detail is None:
        detail = PromptImageDetail.AUTO
    if isinstance(prompt_image, PromptImageUrl):
        url = prompt_image.url
        image_url_obj = ImageURL(url=url, detail=detail.as_openai_detail)
    elif isinstance(prompt_image, PromptImageBase64):
        # TODO: manage image type
        url_with_bytes: str = f"data:image/jpeg;base64,{prompt_image.base_64.decode('utf-8')}"
        image_url_obj = ImageURL(url=url_with_bytes, detail=detail.as_openai_detail)
    elif isinstance(prompt_image, PromptImagePath):
        image_bytes = load_binary_as_base64(path=prompt_image.file_path)
        return await make_image_url_obj(prompt_image=PromptImageBase64(base_64=image_bytes), detail=detail)
    else:
        msg = f"prompt_image of type {type(prompt_image)} is not supported"
        raise LLMPromptParameterError(msg)
    return image_url_obj
