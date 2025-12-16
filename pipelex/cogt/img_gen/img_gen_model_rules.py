from pipelex.types import StrEnum


class ImgGenArgTopic(StrEnum):
    NUM_IMAGES = "num_images"
    ASPECT_RATIO = "aspect_ratio"
    INFERENCE = "inference"
    SAFETY_CHECKER = "safety_checker"
    BACKGROUND = "background"
    SPECIFIC = "specific"


class NumImagesTaxonomy(StrEnum):
    FAL = "fal"
    GPT = "gpt"


class SpecificTaxonomy(StrEnum):
    FAL = "fal"


class AspectRatioTaxonomy(StrEnum):
    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"
    GPT = "gpt"


class InferenceTaxonomy(StrEnum):
    SDXL_LIGHTNING = "sdxl_lightning"
    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"
    GPT = "gpt"


class SafetyCheckerTaxonomy(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class BackgroundTaxonomy(StrEnum):
    GPT = "gpt"


ImgGenModelRules = dict[ImgGenArgTopic, str]
