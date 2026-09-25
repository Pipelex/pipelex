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
    """The console sink's formatter: an emoji for the logger's prefix, then the message, and the record left as it was.

    The prefix goes on in ``formatMessage`` rather than ``format``: the Rich handler renders a record
    that carries ``exc_info`` from ``formatMessage`` alone and discards what ``format`` returned, so a
    prefix built anywhere else vanished from exactly the lines that carry a traceback. The base class's
    ``format`` sets ``record.message``, calls this, and appends the exception text.
    """

    @override
    def formatMessage(self, record: logging.LogRecord) -> str:
        emoji = emoji_for_channel(record.name)
        if emoji == "":
            return record.message
        if emoji:
            return f"{emoji}: {record.message}"
        return f"[{record.name}]: {record.message}"
