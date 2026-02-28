import logging
from typing import Any

from citadel.config_citadel import get_config
from typing_extensions import override

from pipelex.tools.log.log_formatter import LevelAndEmojiLogFormatter, log_level_color, log_level_tag
from pipelex.tools.misc.terminal_utils import RESET_FONT, TerminalColor


class DeepFlowTemporalLogFormatter(LevelAndEmojiLogFormatter):
    @override
    def format(self, record: logging.LogRecord):
        temporal_log_config = get_config().deep_flow.temporal_config.temporal_log_config
        if record.name not in temporal_log_config.managed_loggers:
            return super().format(record)

        # these are prints because we are configuring logs
        # they are commmented but remain as a practical solution to check what temporal injects in logs in various contexts
        # print(f"\n\n{record.name=}")
        # print(f"\n\n{json.dumps(vars(record), default=str)}\n\n")

        prefix = ""

        if temporal_log_config.is_prefix_enabled:
            wf_color = TerminalColor.MAGENTA
            act_color = TerminalColor.CYAN
            if temporal_workflow := getattr(record, "temporal_workflow", None):
                workflow_dict: dict[str, Any] = temporal_workflow
                if workflow_type := workflow_dict.get("workflow_type"):
                    prefix += f"{wf_color}[{workflow_type}]{RESET_FONT}"

            if temporal_activity := getattr(record, "temporal_activity", None):
                activity_dict: dict[str, Any] = temporal_activity
                if workflow_type := activity_dict.get("workflow_type"):
                    prefix += f"{wf_color}[{workflow_type}]{RESET_FONT}"
                if activity_type := activity_dict.get("activity_type"):
                    prefix += f"{act_color}[{activity_type}]{RESET_FONT}"

            if prefix:
                prefix += " "

        color = log_level_color.get(record.levelno, RESET_FONT)
        tag = log_level_tag.get(record.levelno, "?????")

        if record.levelno in {logging.WARNING, logging.ERROR, logging.CRITICAL}:
            record.msg = f"{color}{record.msg}{RESET_FONT}"

        log_fmt = f"{color}{tag}:{prefix}{RESET_FONT} %(message)s"

        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
