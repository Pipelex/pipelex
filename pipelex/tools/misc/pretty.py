import shutil
from typing import Any, ClassVar

from kajson import kajson
from rich import print as rich_print
from rich.console import Group
from rich.json import JSON
from rich.markdown import Markdown
from rich.panel import Panel
from rich.pretty import Pretty
from rich.style import StyleType
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text, TextType

from pipelex.tools.misc.terminal_utils import BOLD_FONT, RESET_FONT, TerminalColor
from pipelex.types import StrEnum

TEXT_COLOR = TerminalColor.WHITE
TITLE_COLOR = TerminalColor.CYAN
BORDER_COLOR = TerminalColor.YELLOW

PRETTY_WIDTH_MIN = 125

PrettyPrintable = Markdown | Text | JSON | Table | Group


def pretty_width(width: int | None = None, factor: float | None = None) -> int:
    terminal_width = shutil.get_terminal_size().columns
    absolute_width = width or min(max(PRETTY_WIDTH_MIN, int(terminal_width / 2)), terminal_width)
    if factor:
        return int(absolute_width * factor)
    return absolute_width


def pretty_print(
    content: str | Any,
    title: TextType | None = None,
    subtitle: TextType | None = None,
    inner_title: str | None = None,
    border_style: StyleType | None = None,
    width: int | None = None,
):
    PrettyPrinter.pretty_print(content=content, title=title, subtitle=subtitle, inner_title=inner_title, border_style=border_style, width=width)


def pretty_print_md(
    content: str,
    title: TextType | None = None,
    subtitle: TextType | None = None,
    inner_title: str | None = None,
    border_style: StyleType | None = None,
    width: int | None = None,
):
    width = width or pretty_width()
    md_content = Markdown(content)
    PrettyPrinter.pretty_print(content=md_content, title=title, subtitle=subtitle, inner_title=inner_title, border_style=border_style, width=width)


class PrettyPrintMode(StrEnum):
    RICH = "rich"
    POOR = "poor"


class PrettyPrinter:
    mode: ClassVar[PrettyPrintMode] = PrettyPrintMode.RICH

    @classmethod
    def pretty_print(
        cls,
        content: str | Any,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
    ):
        match cls.mode:
            case PrettyPrintMode.RICH:
                cls.pretty_print_using_rich(
                    content=content,
                    title=title,
                    subtitle=subtitle,
                    inner_title=inner_title,
                    border_style=border_style,
                    width=width,
                )
            case PrettyPrintMode.POOR:
                cls.pretty_print_without_rich(content=content, title=title, subtitle=subtitle, inner_title=inner_title)

    @classmethod
    def pretty_print_using_rich(
        cls,
        content: str | Any,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
    ):
        if isinstance(content, str):
            if content.startswith(("http://", "https://")):
                content = Text(content, style="link " + content, no_wrap=True)
            else:
                content = Text(str(content))  # Treat all other strings as plain text
        elif isinstance(content, (Pretty, JSON, Table, Markdown, Group)):
            pass
        elif isinstance(content, dict):
            try:
                content = JSON.from_data(content, indent=4)
            except TypeError:
                json_string = kajson.dumps(content, indent=4)
                content = Syntax(json_string, "json", theme="monokai")
        else:
            content = Pretty(content)

        if inner_title:
            inner_title_text = Text(str(inner_title), style="dim")
            content = Group(inner_title_text, content)
        rich_print()
        panel = Panel(
            content,
            title=title,
            subtitle=subtitle,
            expand=False,
            title_align="left",
            subtitle_align="right",
            padding=(1, 1),
            border_style=border_style or "",
            highlight=True,
            width=width,
        )
        rich_print(panel)
        rich_print()

    @classmethod
    def pretty_print_without_rich(
        cls,
        content: str | Any,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
    ):
        if isinstance(content, str) and content.startswith(("http://", "https://")):
            cls.pretty_print_url_without_rich(content=content, title=title, subtitle=subtitle)
            return
        title_str = str(title) if title else ""
        if subtitle:
            title_str += f"\n{subtitle!s}"
        if inner_title:
            title_str += f"\n{inner_title}"
        terminal_width = shutil.get_terminal_size().columns
        content_str = f"{content}"

        # Split title into lines if it contains newlines
        title_lines = title_str.splitlines() if title_str else []

        # Calculate max content width based on longest title line
        max_title_len = max(len(line) for line in title_lines) if title_lines else 0
        max_content_width = terminal_width - max_title_len - 8  # Accounting for frame and padding
        wrapped_lines: list[str] = []
        for line in content_str.splitlines():
            while len(line) > max_content_width:
                wrapped_lines.append(line[:max_content_width])
                line = line[max_content_width:]
            wrapped_lines.append(line)

        if not wrapped_lines:
            wrapped_lines.append("")

        # Calculate frame width based on longest title line and content lines
        max_title_width = max((len(line) for line in title_lines), default=0)
        max_content_line_width = max(len(line) for line in wrapped_lines)
        frame_width = max(max_title_width + 6, max_content_line_width + 6)
        top_border = "╭" + "─" * (frame_width - 2) + "╮"
        bottom_border = "╰" + "─" * (frame_width - 2) + "╯"

        print(f"{BORDER_COLOR}{top_border}{RESET_FONT}")
        # Print each title line separately
        for title_line in title_lines:
            padding = " " * (frame_width - len(title_line) - 4)
            print(f"{BORDER_COLOR}│ {BOLD_FONT}{TITLE_COLOR}{title_line}{RESET_FONT}:{padding}{BORDER_COLOR}│{RESET_FONT}")
        for line in wrapped_lines:
            padding = " " * (frame_width - len(line) - 3)
            print(f"{BORDER_COLOR}│ {TEXT_COLOR}{line}{RESET_FONT}{padding}{BORDER_COLOR}│{RESET_FONT}")
        print(f"{BORDER_COLOR}{bottom_border}{RESET_FONT}")

    @classmethod
    def pretty_print_url_without_rich(
        cls,
        content: str | Any,
        title: TextType | None = None,
        subtitle: TextType | None = None,
    ):
        title = title or ""
        if subtitle:
            title += f" ({subtitle})"
        terminal_width = shutil.get_terminal_size().columns
        frame_width = terminal_width - 2
        top_border = "╭" + "─" * (frame_width - 2) + "╮"
        bottom_border = "╰" + "─" * (frame_width - 2) + "╯"

        print(f"{BORDER_COLOR}{top_border}{RESET_FONT}")
        if title:
            print(f"{BORDER_COLOR}│ {BOLD_FONT}{TITLE_COLOR}{title}{RESET_FONT}:{' ' * (frame_width - len(title) - 4)}{BORDER_COLOR}│{RESET_FONT}")
        print(f"{TEXT_COLOR}{content}{RESET_FONT}")
        print(f"{BORDER_COLOR}{bottom_border}{RESET_FONT}")
