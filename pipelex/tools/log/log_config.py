from __future__ import annotations

import sys
from typing import cast

from pydantic import Field, field_validator
from rich.console import Console
from rich.highlighter import Highlighter, JSONHighlighter, ReprHighlighter
from rich.logging import RichHandler

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_levels import LogLevel
from pipelex.types import StrEnum


class LogMode(StrEnum):
    RICH = "rich"
    POOR = "poor"


class HighlighterName(StrEnum):
    JSON = "json"
    REPR = "repr"


class ProblemIds(StrEnum):
    AZURE_OPENAI_NO_STREAM_OPTIONS = "Azure OpenAI no stream_options"


class CallerInfoTemplate(StrEnum):
    FILE_LINE = "file_line"
    FILE_LINE_FUNC = "file_line_func"
    FUNC = "func"
    FILE_FUNC = "file_func"
    FUNC_LINE = "func_line"
    FUNC_MODULE = "func_module"
    FUNC_MODULE_LINE = "func_module_line"

    @classmethod
    def for_template_key(cls, key: CallerInfoTemplate) -> str:
        match key:
            case cls.FILE_LINE:
                return "{file}:{line}"
            case cls.FILE_LINE_FUNC:
                return "{file}:{line} {func}"
            case cls.FUNC:
                return "{func}"
            case cls.FILE_FUNC:
                return "{file} {func}"
            case cls.FUNC_LINE:
                return "{func} {line}"
            case cls.FUNC_MODULE:
                return "{func} {module}"
            case cls.FUNC_MODULE_LINE:
                return "{func} {module} {line}"


class RichLogConfig(ConfigModel):
    is_show_time: bool
    is_show_level: bool
    is_link_path_enabled: bool
    highlighter_name: HighlighterName = Field(strict=False)
    is_markup_enabled: bool
    is_rich_tracebacks: bool
    is_tracebacks_word_wrap: bool
    is_tracebacks_show_locals: bool
    tracebacks_suppress: list[str]
    keywords_to_hilight: list[str]

    def make_rich_handler(self, target: ConsoleTarget) -> RichHandler:
        match target:
            case ConsoleTarget.STDOUT:
                console = Console(file=sys.stdout)
            case ConsoleTarget.STDERR:
                console = Console(file=sys.stderr)
            # case ConsoleTarget.FILE:
            #     console = Console(file=target.file_path)
            case _:
                msg = f"Invalid console target: {target}"
                raise ValueError(msg)
        highlighter: Highlighter
        match self.highlighter_name:
            case HighlighterName.JSON:
                highlighter = JSONHighlighter()
            case HighlighterName.REPR:
                highlighter = ReprHighlighter()

        return RichHandler(
            console=console,
            show_time=self.is_show_time,
            show_level=self.is_show_level,
            enable_link_path=self.is_link_path_enabled,
            highlighter=highlighter,
            markup=self.is_markup_enabled,
            rich_tracebacks=self.is_rich_tracebacks,
            tracebacks_word_wrap=self.is_tracebacks_word_wrap,
            tracebacks_show_locals=self.is_tracebacks_show_locals,
            tracebacks_suppress=self.tracebacks_suppress,
            keywords=self.keywords_to_hilight,
        )


class LogConfig(ConfigModel):
    default_log_level: LogLevel = Field(strict=False)
    package_log_levels: dict[str, LogLevel]
    log_mode: LogMode = Field(strict=False)
    console_log_target: ConsoleTarget = Field(strict=False)
    console_print_target: ConsoleTarget = Field(strict=False)

    is_console_logging_enabled: bool

    json_logs_indent: int
    presentation_line_width: int
    is_caller_info_enabled: bool
    caller_info_template: CallerInfoTemplate = Field(strict=False)

    silenced_problem_ids: list[str]

    rich_log_config: RichLogConfig

    # logger name to use for safe logging without fancy features like code filepath and stuff
    generic_poor_logger: str
    poor_loggers: list[str]

    @field_validator("package_log_levels", mode="before")
    @classmethod
    def validate_package_log_levels(cls, value: dict[str, str]) -> dict[str, LogLevel]:
        return cast(
            "dict[str, LogLevel]",
            ConfigModel.transform_dict_str_to_enum(input_dict=value, value_enum_cls=LogLevel),
        )
