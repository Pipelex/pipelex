"""Image generation model rules and taxonomy definitions.

This module defines the parameter mapping strategies (taxonomies) for different image generation
model backends. Each taxonomy enum specifies HOW a high-level parameter should be translated
into the specific API parameters expected by different providers (Fal, OpenAI, etc.).

For example, to request a square image:
- Flux models use `image_size: "square_hd"`
- GPT models use `size: "1024x1024"`

The taxonomy system allows the factory to generate the correct API arguments for each model
without hardcoding provider-specific logic throughout the codebase.
"""

from pipelex.types import StrEnum


class ImgGenArgTopic(StrEnum):
    """Topics/categories of arguments that can be configured for image generation.

    Each topic represents a parameter category that may have different mapping strategies
    depending on the model backend being used.
    """

    MODEL_NAME = "model_name"
    PROMPT = "prompt"
    NUM_IMAGES = "num_images"
    ASPECT_RATIO = "aspect_ratio"
    INFERENCE = "inference"
    SAFETY_CHECKER = "safety_checker"
    BACKGROUND = "background"
    OUTPUT_FORMAT = "output_format"
    SPECIFIC = "specific"
    INPUT_IMAGES = "input_images"
    INPUT_FIDELITY = "input_fidelity"


class NumImagesTaxonomy(StrEnum):
    """Taxonomy for mapping the number of images parameter.

    Different providers use different parameter names:
    - FAL: uses `num_images`
    - GPT: uses `n`
    """

    FAL = "fal"
    GPT = "gpt"


class SpecificTaxonomy(StrEnum):
    """Taxonomy for provider-specific parameters not covered by other taxonomies.

    - FAL: includes settings like `sync_mode`
    """

    FAL = "fal"


class PromptTaxonomy(StrEnum):
    """Taxonomy for prompt parameters.

    Different models may use different parameter names and support different prompt types:
    - POSITIVE_ONLY: uses `prompt` for positive text, no negative prompt support
    - WITH_NEGATIVE: uses `prompt` for positive text and `negative_prompt` for negative text
    """

    POSITIVE_ONLY = "positive_only"
    WITH_NEGATIVE = "with_negative"


class AspectRatioTaxonomy(StrEnum):
    """Taxonomy for mapping aspect ratio parameters.

    Different providers use different parameter names and value formats:
    - FLUX: uses `image_size` with values like "square_hd", "landscape_4_3"
    - FLUX_11_ULTRA: uses `aspect_ratio` with values like "1:1", "4:3"
    - OPENAI_GPT_IMAGE_LEGACY: uses fixed OpenAI GPT Image sizes
    - OPENAI_GPT_IMAGE_2: validates and forwards exact OpenAI GPT Image 2 sizes
    - QWEN_IMAGE: uses `width` and `height` with pixel dimensions mapped from aspect ratios
      (e.g., "1:1" -> 1328x1328, "16:9" -> 1664x928, "9:16" -> 928x1664,
       "4:3" -> 1472x1140, "3:4" -> 1140x1472, "3:2" -> 1584x1056, "2:3" -> 1056x1584)
    """

    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"
    GPT = "gpt"
    OPENAI_GPT_IMAGE_LEGACY = "openai_gpt_image_legacy"
    OPENAI_GPT_IMAGE_2 = "openai_gpt_image_2"
    QWEN_IMAGE = "qwen_image"


class InferenceTaxonomy(StrEnum):
    """Taxonomy for mapping inference-related parameters (steps, quality, guidance).

    Different models have different inference parameters and quality mappings:
    - SDXL_LIGHTNING: uses `num_inference_steps` (valid: 1, 2, 4, 8)
    - FLUX: uses `num_inference_steps` and `guidance_scale`
    - FLUX_11_ULTRA: uses `raw` mode
    - GPT: uses `quality` ("low", "medium", "high")
    - QWEN_IMAGE: uses `num_inference_steps` and `guidance_scale`
    """

    SDXL_LIGHTNING = "sdxl_lightning"
    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"
    GPT = "gpt"
    QWEN_IMAGE = "qwen_image"


class SafetyCheckerTaxonomy(StrEnum):
    """Taxonomy for safety checker availability.

    - AVAILABLE: model supports `enable_safety_checker` and `safety_tolerance` parameters
    - OPENAI_MODERATION: model supports OpenAI `moderation` parameter
    - UNAVAILABLE: model does not expose safety checker configuration
    """

    AVAILABLE = "available"
    OPENAI_MODERATION = "openai_moderation"
    UNAVAILABLE = "unavailable"


class BackgroundTaxonomy(StrEnum):
    """Taxonomy for background transparency/removal parameters.

    - AVAILABLE: supports `background` parameter for transparency control
    - UNAVAILABLE: model does not support setting background; the parameter is skipped
      and requesting a transparent background raises ImgGenParameterError
    """

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class OutputFormatTaxonomy(StrEnum):
    """Taxonomy for output format parameters.

    Different models use different parameter names and support different formats:
    - SDXL: uses `format`, supports png/jpeg only
    - FLUX_1: uses `output_format`, supports png/jpeg only
    - FLUX_2: uses `output_format`, supports png/jpeg/webp
    - GPT: uses `output_format`, supports png/jpeg/webp
    """

    SDXL = "sdxl"
    FLUX_1 = "flux_1"
    FLUX_2 = "flux_2"
    GPT = "gpt"
    UNAVAILABLE = "unavailable"


class ModelNameTaxonomy(StrEnum):
    """Taxonomy for how model name/id is passed to the API.

    - STANDARD: passes model as {"model": model_id}
    """

    STANDARD = "standard"


class InputImagesTaxonomy(StrEnum):
    """Taxonomy for mapping input images to API format for image-to-image generation.

    Different providers accept input images in different formats:
    - GPT_IMAGE: OpenAI gpt-image-1/1.5 format with `image` array of base64 data URLs
    - BFL_FLUX_2: BFL Flux 2 Pro format with `input_image`, `input_image_2`, etc.
    - NONE: Model does not support image inputs
    """

    GPT_IMAGE = "gpt_image"
    BFL_FLUX_2 = "bfl_flux_2"
    NONE = "none"


class InputFidelityTaxonomy(StrEnum):
    """Taxonomy for image-editing fidelity controls.

    - OPENAI_IMAGE: OpenAI GPT Image edit `input_fidelity`, values "low" or "high"
    - UNAVAILABLE: model does not support input fidelity configuration
    """

    OPENAI_IMAGE = "openai_image"
    UNAVAILABLE = "unavailable"


ImgGenModelRules = dict[ImgGenArgTopic, str]
