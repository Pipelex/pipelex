from pipelex.plugins.openai.openai_factory import OpenAIFactory


class OpenAIFactoryAlt(OpenAIFactory):
    def __init__(self, is_http_url_enabled: bool):
        super().__init__()
        self.is_http_url_enabled = is_http_url_enabled

    # @override
    # async def make_image_url_obj(self, prompt_image: PromptImage, detail: PromptImageDetail | None) -> ImageURL:
    #     if detail is None:
    #         detail = PromptImageDetail.AUTO
    #     if isinstance(prompt_image, PromptImageUrl):
    #         if self.is_http_url_enabled:
    #             url = prompt_image.url
    #             openai_image_url = ImageURL(url=url, detail=detail.as_openai_detail)
    #         else:
    #             # we can't use an actual HTTP URL, so we need to download the image and use a base64-encoded string
    #             image_bytes = await PromptImageFactory.make_promptimagebase64_from_url_async(prompt_image_url=prompt_image)
    #             file_type = detect_file_type_from_base64(image_bytes.base_64)
    #             typed_bytes_or_url = PromptImageTypedBase64(base_64=image_bytes.base_64, file_type=file_type)
    #     elif isinstance(prompt_image, PromptImageBase64):
    #         # TODO: manage image type
    #         url_with_bytes: str = f"data:image/jpeg;base64,{prompt_image.base_64.decode('utf-8')}"
    #         openai_image_url = ImageURL(url=url_with_bytes, detail=detail.as_openai_detail)
    #     elif isinstance(prompt_image, PromptImagePath):
    #         image_bytes = load_binary_as_base64(path=prompt_image.file_path)
    #         return self.make_image_url_obj(prompt_image=PromptImageBase64(base_64=image_bytes), detail=detail)
    #     else:
    #         msg = f"prompt_image of type {type(prompt_image)} is not supported"
    #         raise LLMPromptParameterError(msg)
    #     return openai_image_url
