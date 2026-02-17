from pipelex.system.configuration.config_model import ConfigModel


class MthdsConfigStrings(ConfigModel):
    prefer_literal: bool
    force_multiline: bool
    length_limit_to_multiline: int
    ensure_trailing_newline: bool
    ensure_leading_blank_line: bool


class MthdsConfigInlineTables(ConfigModel):
    spaces_inside_curly_braces: bool


class MthdsConfigForConcepts(ConfigModel):
    structure_field_ordering: list[str]


class MthdsConfigForPipes(ConfigModel):
    field_ordering: list[str]


class MthdsConfig(ConfigModel):
    strings: MthdsConfigStrings
    inline_tables: MthdsConfigInlineTables
    concepts: MthdsConfigForConcepts
    pipes: MthdsConfigForPipes
