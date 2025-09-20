from pipelex.types import StrEnum


# List of classic Img generation preset handles, for convenience
class ImggHandle(StrEnum):
    FLUX_1_PRO_LEGACY = "fal-ai/flux-pro"
    FLUX_1_1_PRO = "fal-ai/flux-pro/v1.1"
    FLUX_1_1_ULTRA = "fal-ai/flux-pro/v1.1-ultra"
    SDXL_LIGHTNING = "fal-ai/fast-lightning-sdxl"
    OPENAI_GPT_IMAGE_1 = "openai/gpt-image-1"
