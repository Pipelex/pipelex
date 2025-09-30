from pipelex.config.config_model import ConfigModel


class GenricTemplatesConfig(ConfigModel):
    structure_from_preliminary_text_user: str
    structure_from_preliminary_text_system: str


class TemplatesConfig(ConfigModel):
    generic_templates: GenricTemplatesConfig
