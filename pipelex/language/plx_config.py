from pipelex.system.configuration.config_model import ConfigModel


class PlxConfigStrings(ConfigModel):
    prefer_literal: bool
    force_multiline: bool
    length_limit_to_multiline: int
    ensure_trailing_newline: bool
    ensure_leading_blank_line: bool


class PlxConfigInlineTables(ConfigModel):
    spaces_inside_curly_braces: bool


class PlxConfigForConcepts(ConfigModel):
    structure_field_ordering: list[str]


class PlxConfigForPipes(ConfigModel):
    field_ordering: list[str]


class PlxConfig(ConfigModel):
    strings: PlxConfigStrings
    inline_tables: PlxConfigInlineTables
    concepts: PlxConfigForConcepts
    pipes: PlxConfigForPipes
