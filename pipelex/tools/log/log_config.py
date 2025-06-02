from enum import Enum
from typing import Dict, List, cast

from pydantic import Field, field_validator
from rich.highlighter import Highlighter, JSONHighlighter, ReprHighlighter
from rich.logging import RichHandler

from pipelex.tools.config.models import ConfigModel
from pipelex.tools.log.log_levels import LogLevel
from pipelex.types import StrEnum


class HighlighterName(StrEnum):
    JSON = "json"
    REPR = "repr"


class PROBLEM_IDS(StrEnum):
    AZURE_OPENAI_NO_STREAM_OPTIONS = "Azure OpenAI no stream_options"


class CallerInfoTemplate(Enum):
    FILE_LINE = "file_line"
    FILE_LINE_FUNC = "file_line_func"
    FUNC = "func"
    FILE_FUNC = "file_func"
    FUNC_LINE = "func_line"
    FUNC_MODULE = "func_module"
    FUNC_MODULE_LINE = "func_module_line"

    @classmethod
    def for_template_key(cls, key: "CallerInfoTemplate") -> str:
        templates: Dict[CallerInfoTemplate, str] = {
            cls.FILE_LINE: "{file}:{line}",
            cls.FILE_LINE_FUNC: "{file}:{line} {func}",
            cls.FUNC: "{func}",
            cls.FILE_FUNC: "{file} {func}",
            cls.FUNC_LINE: "{func} {line}",
            cls.FUNC_MODULE: "{func} {module}",
            cls.FUNC_MODULE_LINE: "{func} {module} {line}",
        }
        return templates.get(key, "")


class RichLogConfig(ConfigModel):
    is_show_time: bool
    is_show_level: bool
    is_link_path_enabled: bool
    highlighter_name: HighlighterName = Field(strict=False)
    is_markup_enabled: bool
    is_rich_tracebacks: bool
    is_tracebacks_word_wrap: bool
    is_tracebacks_show_locals: bool
    tracebacks_suppress: List[str]
    keywords_to_hilight: List[str]

    def make_rich_handler(self) -> RichHandler:
        highlighter: Highlighter
        match self.highlighter_name:
            case HighlighterName.JSON:
                highlighter = JSONHighlighter()
            case HighlighterName.REPR:
                highlighter = ReprHighlighter()

        return RichHandler(
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
    package_log_levels: Dict[str, LogLevel]

    is_console_logging_enabled: bool

    json_logs_indent: int
    presentation_line_width: int
    is_caller_info_enabled: bool
    caller_info_template: CallerInfoTemplate = Field(strict=False)

    silenced_problem_ids: List[str]

    rich_log_config: RichLogConfig

    # logger name to use for safe logging without fancy features like code filepath and stuff
    generic_poor_logger: str
    poor_loggers: List[str]

    @field_validator("package_log_levels", mode="before")
    def validate_package_log_levels(cls, value: Dict[str, str]) -> Dict[str, LogLevel]:
        """
        Validate the package log levels dictionary.
        """
        the_dict = cast(
            Dict[str, LogLevel],
            ConfigModel.transform_dict_str_to_enum(input_dict=value, value_enum_cls=LogLevel),
        )
        return the_dict
