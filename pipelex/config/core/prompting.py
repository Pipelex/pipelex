from pipelex.cogt.model_backends.prompting_target import PromptingTarget
from pipelex.config.config_model import ConfigModel
from pipelex.tools.templating.templating_models import PromptingStyle


class PromptingConfig(ConfigModel):
    default_prompting_style: PromptingStyle
    prompting_styles: dict[str, PromptingStyle]

    def get_prompting_style(self, prompting_target: PromptingTarget | None = None) -> PromptingStyle | None:
        if prompting_target:
            return self.prompting_styles.get(prompting_target, self.default_prompting_style)
        return None
