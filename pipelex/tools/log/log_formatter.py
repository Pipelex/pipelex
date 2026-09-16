import logging

from typing_extensions import override


# TODO: move these to the config
def emoji_for_channel(channel_name: str) -> str | None:
    channel_emojis: dict[str, str] = {
        "root": "",
        "werkzeug": "📡",
        "urllib3.connectionpool": "⚡️",
    }

    emoji = channel_emojis.get(channel_name)
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
    elif channel_name.startswith("pipelex"):
        return "🧠"
    else:
        return None


class EmojiLogFormatter(logging.Formatter):
    """The console sink's formatter: an emoji for the logger's prefix, then the message, and the record left as it was."""

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
