from typing import Dict

from pipelex.tools.config.models import ConfigModel


class SpecificLLMConfig(ConfigModel):
    llm_worker_classes: Dict[str, str]
