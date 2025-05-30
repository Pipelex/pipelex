import shutil
from typing import Any, List, Optional, Union

from kajson.sandbox_manager import sandbox_manager
from rich import print as rich_print
from rich.panel import Panel
from rich.pretty import Pretty
from rich.style import StyleType
from rich.table import Table
from rich.text import Text, TextType

from pipelex.tools.misc.terminal_utils import BOLD_FONT, RESET_FONT, TerminalColor

TEXT_COLOR = TerminalColor.WHITE
TITLE_COLOR = TerminalColor.CYAN
BORDER_COLOR = TerminalColor.YELLOW


def pretty_print(
    content: Union[str, Any],
    title: Optional[TextType] = None,
    subtitle: Optional[TextType] = None,
    border_style: Optional[StyleType] = None,
):
    if sandbox_manager.is_in_sandbox():
        # we are in a sandbox, so we can't use rich
        pretty_print_in_sandbox(content=content, title=title, subtitle=subtitle)
    else:
        pretty_print_using_rich(content=content, title=title, subtitle=subtitle, border_style=border_style)


def pretty_print_using_rich(
    content: Union[str, Any],
    title: Optional[TextType] = None,
    subtitle: Optional[TextType] = None,
    border_style: Optional[StyleType] = None,
):
    if isinstance(content, str):
        if content.startswith(("http://", "https://")):
            content = Text(content, style="link " + content, no_wrap=True)
        else:
            content = Text(str(content))  # Treat all other strings as plain text
    elif isinstance(content, Table):
        # For tables, print directly without a panel
        if title:
            rich_print(f"\n[bold blue]{title}[/]\n")
        rich_print(content)
        rich_print("\n")
        if subtitle:
            rich_print(f"\n[dim]{subtitle}[/]")
        return
    else:
        content = Pretty(content)
    panel = Panel(
        content,
        title=title,
        subtitle=subtitle,
        expand=False,
        title_align="left",
        subtitle_align="right",
        padding=(0, 1),
        border_style=border_style or "",
    )
    rich_print(panel)


def pretty_print_in_sandbox(
    content: Union[str, Any],
    title: Optional[TextType] = None,
    subtitle: Optional[TextType] = None,
):
    if isinstance(content, str) and content.startswith(("http://", "https://")):
        pretty_print_url_in_sandbox(content=content, title=title, subtitle=subtitle)
        return
    title = title or ""
    if subtitle:
        title += f" ({subtitle})"
    terminal_width = shutil.get_terminal_size().columns
    content_str = f"{content}"
    max_content_width = terminal_width - len(title) - 8  # Accounting for frame and padding
    wrapped_lines: List[str] = []
    for line in content_str.splitlines():
        while len(line) > max_content_width:
            wrapped_lines.append(line[:max_content_width])
            line = line[max_content_width:]
        wrapped_lines.append(line)

    if not wrapped_lines:
        wrapped_lines.append("")

    frame_width = max(len(title) + 6, max(len(line) for line in wrapped_lines) + 6)
    top_border = "╭" + "─" * (frame_width - 2) + "╮"
    bottom_border = "╰" + "─" * (frame_width - 2) + "╯"

    print(f"{BORDER_COLOR}{top_border}{RESET_FONT}")
    if title:
        print(f"{BORDER_COLOR}│ {BOLD_FONT}{TITLE_COLOR}{title}{RESET_FONT}:{' ' * (frame_width - len(title) - 4)}{BORDER_COLOR}│{RESET_FONT}")
    for line in wrapped_lines:
        padding = " " * (frame_width - len(line) - 3)
        print(f"{BORDER_COLOR}│ {TEXT_COLOR}{line}{RESET_FONT}{padding}{BORDER_COLOR}│{RESET_FONT}")
    print(f"{BORDER_COLOR}{bottom_border}{RESET_FONT}")


def pretty_print_url_in_sandbox(
    content: Union[str, Any],
    title: Optional[TextType] = None,
    subtitle: Optional[TextType] = None,
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
