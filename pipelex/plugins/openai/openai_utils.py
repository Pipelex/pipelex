import base64

from openai.types.chat.chat_completion_content_part_image_param import ImageURL

from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImageBinary,
    PromptImageDetail,
    PromptImageUri,
)
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)


async def make_image_url_obj(prompt_image: PromptImage, detail: PromptImageDetail | None) -> ImageURL:
    """Convert a PromptImage to an OpenAI ImageURL object.

    Args:
        prompt_image: The input prompt image
        detail: Image detail level (high, low, or auto)

    Returns:
        An ImageURL object ready for OpenAI API
    """
    if detail is None:
        detail = PromptImageDetail.AUTO

    url: str
    match prompt_image:
        case PromptImageUri():
            match prompt_image.resolved:
                case ResolvedHttpUrl():
                    url = prompt_image.resolved.url
                case ResolvedLocalPath():
                    raw_bytes = await load_binary_async(path=prompt_image.resolved.path)
                    encoded_bytes = base64.b64encode(raw_bytes)
                    file_type = detect_file_type_from_bytes(raw_bytes)
                    url = f"data:{file_type.mime};base64,{encoded_bytes.decode('utf-8')}"
                case ResolvedBase64DataUrl():
                    # Already a data URL, reconstruct it
                    url = prompt_image.uri
                case ResolvedPipelexStorage():
                    msg = f"Pipelex storage URIs not supported in openai_utils: {prompt_image.uri}"
                    raise LLMPromptParameterError(msg)

        case PromptImageBase64():
            file_type = prompt_image.get_file_type()
            url = f"data:{file_type.mime};base64,{prompt_image.base64_bytes.decode('utf-8')}"

        case PromptImageBinary():
            file_type = prompt_image.get_file_type()
            encoded_bytes = base64.b64encode(prompt_image.binary_bytes)
            url = f"data:{file_type.mime};base64,{encoded_bytes.decode('utf-8')}"

    return ImageURL(url=url, detail=detail.as_openai_detail)
