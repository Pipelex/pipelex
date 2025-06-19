import logging
from typing import Dict, Optional

from typing_extensions import override

from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_VERBOSE
from pipelex.tools.misc.terminal_utils import BOLD_FONT, RESET_FONT, TerminalColor


# TODO: move these to the config
def emoji_for_channel(channel_name: str) -> Optional[str]:
    channel_emojis: Dict[str, str] = {
        "root": "",
        "werkzeug": "📡",
        "urllib3.connectionpool": "⚡️",
    }

    emoji = channel_emojis.get(channel_name, None)
    if emoji == "":
        # blank emoji is OK
        return emoji
    elif emoji:
        return emoji
    elif channel_name.startswith("google"):
        return "🌀"
    elif channel_name.startswith("openai"):
        return "⚪️"
    elif channel_name.startswith("kajson"):
        # space added to make it look better
        return "*️⃣ "
    elif channel_name.startswith("#poor-log"):
        # space added to make it look better
        return "🧿 "
    elif channel_name.startswith("pipelex"):
        return "🧠"
    else:
        return None


class EmojiLogFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord):
        log_fmt: str
        emoji = emoji_for_channel(record.name)
        if emoji == "":
            log_fmt = "%(message)s"
        elif emoji:
            log_fmt = f"{emoji}: %(message)s"
        else:
            log_fmt = "[%(name)s]: %(message)s"
        formatter = logging.Formatter(log_fmt)

        return formatter.format(record)


log_level_color: Dict[int, TerminalColor] = {
    LOGGING_LEVEL_VERBOSE: TerminalColor.WHITE,
    logging.DEBUG: TerminalColor.GREEN,
    LOGGING_LEVEL_DEV: TerminalColor.CYAN,
    logging.INFO: TerminalColor.BLUE,
    logging.WARNING: TerminalColor.YELLOW,
    logging.ERROR: TerminalColor.RED,
    logging.CRITICAL: TerminalColor.MAGENTA,
}

# added spaces and truncated to 5 characters to make it look better
log_level_tag: Dict[int, str] = {
    LOGGING_LEVEL_VERBOSE: "VERBO",
    logging.DEBUG: "DEBUG",
    LOGGING_LEVEL_DEV: "DEV  ",
    logging.INFO: "INFO ",
    logging.WARNING: f"{BOLD_FONT}WARNING{RESET_FONT}",
    logging.ERROR: f"{BOLD_FONT}/ERROR\\{RESET_FONT}",
    logging.CRITICAL: f"{BOLD_FONT}CRITICAL{RESET_FONT}",
}


class LevelAndEmojiLogFormatter(logging.Formatter):
    @override
    def format(self, record: logging.LogRecord):
        emoji = emoji_for_channel(record.name)
        color = log_level_color.get(record.levelno, RESET_FONT)
        tag = log_level_tag.get(record.levelno, "?????")
        if emoji:
            log_fmt = f"{emoji} {color}{tag}:{RESET_FONT} %(message)s"
        else:
            log_fmt = f"{color}{tag}:%(name)s{RESET_FONT} %(message)s"
        formatter = logging.Formatter(log_fmt)

        if record.levelno in [logging.WARNING, logging.ERROR, logging.CRITICAL]:
            record.msg = f"{color}{BOLD_FONT}{record.msg}{RESET_FONT}"

        return formatter.format(record)
