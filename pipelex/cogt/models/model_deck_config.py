from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.runtime import ProblemReaction


class ModelDeckConfig(ConfigModel):
    is_model_fallback_enabled: bool
    missing_presets_reaction: ProblemReaction = Field(strict=False)
