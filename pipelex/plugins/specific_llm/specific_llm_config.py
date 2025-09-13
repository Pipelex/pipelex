from typing import Dict

from pipelex.tools.config.config_model import ConfigModel


class SpecificLLMConfig(ConfigModel):
    llm_worker_classes: Dict[str, str]
