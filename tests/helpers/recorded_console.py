"""A Rich console whose output a test reads back."""

from io import StringIO
from typing import NamedTuple

from rich.console import Console


class RecordedConsole(NamedTuple):
    console: Console
    buffer: StringIO

    def text(self) -> str:
        return self.buffer.getvalue()


def make_recorded_console() -> RecordedConsole:
    buffer = StringIO()
    return RecordedConsole(console=Console(file=buffer, width=200), buffer=buffer)
