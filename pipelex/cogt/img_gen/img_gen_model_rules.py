from pipelex.types import StrEnum


class ImgGenArgTopic(StrEnum):
    ASPECT_RATIO = "aspect_ratio"
    INFERENCE = "inference"
    SAFETY_CHECKER = "safety_checker"


class AspectRatioTaxonomy(StrEnum):
    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"


class InferenceTaxonomy(StrEnum):
    SDXL_LIGHTNING = "sdxl_lightning"
    FLUX = "flux"
    FLUX_11_ULTRA = "flux_11_ultra"


class SafetyCheckerTaxonomy(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


ImgGenModelRules = dict[ImgGenArgTopic, str]
