from __future__ import annotations

import re
from enum import StrEnum
from typing import cast

from pydantic import Field, field_validator

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.misc.pretty import PrettyPrintMode


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
    """The settings of the ``console`` sink's Rich handler. Read by the sink; this module imports no Rich."""

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


class OtlpLogSinkConfig(ConfigModel):
    """The settings of the ``otlp`` sink.

    An absent ``endpoint`` leaves the exporter to the OpenTelemetry environment conventions:
    ``OTEL_EXPORTER_OTLP_LOGS_ENDPOINT``, then ``OTEL_EXPORTER_OTLP_ENDPOINT`` with the ``/v1/logs``
    path, then the collector default on localhost. Empty ``headers`` likewise leave
    ``OTEL_EXPORTER_OTLP_HEADERS`` in charge.
    """

    endpoint: str | None = None
    headers: dict[str, str]


class LogRedactionConfig(ConfigModel):
    """What the redaction processor removes from a record before any sink renders it.

    ``is_enabled`` turns the processor off for a process that redacts downstream, or one whose records
    must be reproduced exactly as the call made them. ``extra_patterns`` are regular expressions a
    deployment adds to the shipped families, for the secret shapes only it knows: every match is
    replaced by the redaction text. A pattern the ``re`` module refuses is a configuration error named
    at load rather than a boot that dies later on a regex nobody can see.
    """

    is_enabled: bool
    extra_patterns: list[str]

    @field_validator("extra_patterns")
    @classmethod
    def validate_extra_patterns(cls, value: list[str]) -> list[str]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as exc:
                msg = f"extra_patterns under [runtime.log.redaction] holds a regular expression the re module refuses: '{pattern}' ({exc})"
                raise ValueError(msg) from exc
        return value


class LogConfig(ConfigModel):
    default_log_level: LogLevel = Field(strict=False)
    package_log_levels: dict[str, LogLevel]
    # The registered log-sink token boot selects: an open string, validated at the registry lookup.
    sink: str
    pretty_print_mode: PrettyPrintMode = Field(strict=False)
    console_log_target: ConsoleTarget = Field(strict=False)
    console_print_target: ConsoleTarget = Field(strict=False)

    json_logs_indent: int
    presentation_line_width: int
    is_caller_info_enabled: bool
    caller_info_template: CallerInfoTemplate = Field(strict=False)

    silenced_problem_ids: list[str]

    redaction: LogRedactionConfig
    rich_log: RichLogConfig
    otlp: OtlpLogSinkConfig

    @field_validator("package_log_levels", mode="before")
    @classmethod
    def validate_package_log_levels(cls, value: dict[str, str]) -> dict[str, LogLevel]:
        return cast(
            "dict[str, LogLevel]",
            ConfigModel.transform_dict_str_to_enum(input_dict=value, value_enum_cls=LogLevel),
        )
