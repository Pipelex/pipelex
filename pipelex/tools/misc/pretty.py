import shutil
from abc import ABC, abstractmethod
from io import StringIO
from typing import Any, ClassVar

from kajson import kajson
from pydantic import BaseModel
from rich.console import Console, Group
from rich.json import JSON
from rich.markdown import Markdown
from rich.measure import Measurement
from rich.panel import Panel
from rich.pretty import Pretty
from rich.style import StyleType
from rich.syntax import Syntax
from rich.table import Table
from rich.terminal_theme import TerminalTheme
from rich.text import Text, TextType

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.terminal_utils import BOLD_FONT, RESET_FONT, TerminalColor, print_to_stderr
from pipelex.tools.typing.pydantic_utils import make_truncated_wrapper
from pipelex.types import StrEnum

TEXT_COLOR = TerminalColor.WHITE
TITLE_COLOR = TerminalColor.CYAN
BORDER_COLOR = TerminalColor.YELLOW

# TODO: Make PrettyPrinter a manager so we can init it with a proper config
PRETTY_WIDTH_MIN: int = 125
PRETTY_WIDTH_FOR_EXPORT: int = 100
MAX_RENDER_DEPTH = 6
EXPORT_THEME = TerminalTheme(
    (0, 0, 0),
    (197, 200, 198),
    [
        (75, 78, 85),
        (204, 85, 90),
        (152, 168, 75),
        (208, 179, 68),
        (96, 138, 177),
        (152, 114, 159),
        (104, 160, 179),
        (197, 200, 198),
        (154, 155, 153),
    ],
    [
        (255, 38, 39),
        (0, 130, 61),
        (208, 132, 66),
        (25, 132, 233),
        (255, 44, 122),
        (57, 130, 128),
        (253, 253, 197),
    ],
)

PrettyPrintable = Markdown | Text | JSON | Table | Group | Syntax | Pretty


class PrettyRenderable(ABC):
    @abstractmethod
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        pass

    def rendered_pretty_text(self, title: str | None = None, width: int = PRETTY_WIDTH_FOR_EXPORT) -> str:
        """Render as plain ASCII text string.

        Args:
            title: Optional title for the rendering
            width: Console width for text wrapping

        Returns:
            Plain text string representation
        """
        pretty = self.rendered_pretty(title=title, depth=0)
        return PrettyPrinter.pretty_text(pretty, width=width)

    def rendered_pretty_html(self, title: str | None = None, width: int | None = None) -> str:
        """Render as HTML string.

        Args:
            title: Optional title for the rendering
            width: Optional console width for layout

        Returns:
            HTML string representation
        """
        pretty = self.rendered_pretty(title=title, depth=0)
        return PrettyPrinter.pretty_html(pretty, width=width or PRETTY_WIDTH_FOR_EXPORT)


class PrettyPrintMode(StrEnum):
    RICH = "rich"
    POOR = "poor"


def pretty_print(
    content: str | Any,
    title: TextType | None = None,
    subtitle: TextType | None = None,
    inner_title: str | None = None,
    border_style: StyleType | None = None,
    width: int | None = None,
    console_width: int | None = None,
):
    PrettyPrinter.pretty_print(
        content=content,
        title=title,
        subtitle=subtitle,
        inner_title=inner_title,
        border_style=border_style,
        width=width,
        console_width=console_width,
    )


def pretty_print_md(
    content: str,
    title: TextType | None = None,
    subtitle: TextType | None = None,
    inner_title: str | None = None,
    border_style: StyleType | None = None,
    width: int | None = None,
    console_width: int | None = None,
):
    width = width or PrettyPrinter.pretty_width()
    md_content = Markdown(content)
    PrettyPrinter.pretty_print(
        content=md_content,
        title=title,
        subtitle=subtitle,
        inner_title=inner_title,
        border_style=border_style,
        width=width,
        console_width=console_width,
    )


def pretty_print_url(
    url: str,
    title: TextType | None = None,
    subtitle: TextType | None = None,
    inner_title: str | None = None,
    border_style: StyleType | None = None,
    width: int | None = None,
    console_width: int | None = None,
):
    if url.startswith("/"):
        url = "file://" + url
    pretty_print(
        Text(url, style="link " + url, no_wrap=False),
        title=title,
        subtitle=subtitle,
        inner_title=inner_title,
        border_style=border_style,
        width=width,
        console_width=console_width,
    )


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
        console_width: int | None = None,
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
                    console_width=console_width,
                )
            case PrettyPrintMode.POOR:
                cls.pretty_print_without_rich(content=content, title=title, subtitle=subtitle, inner_title=inner_title, console_width=console_width)

    @classmethod
    def pretty_print_using_rich(
        cls,
        content: str | Any,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
        console_width: int | None = None,
    ):
        panel = cls.make_pretty_panel(
            content=content,
            title=title,
            subtitle=subtitle,
            inner_title=inner_title,
            border_style=border_style,
            width=width,
            console_width=console_width,
        )

        Console(width=console_width).print("", panel, "", sep="\n")

    @classmethod
    def pretty_width(cls, width: int | None = None, depth: int | None = None) -> int:
        terminal_width = shutil.get_terminal_size().columns
        absolute_width = width or min(max(PRETTY_WIDTH_MIN, terminal_width // 2), terminal_width)
        if depth is not None:
            # Calculate adaptive width factor based on depth to prevent excessive narrowing
            # Factor decreases slowly: depth 0->1.0, depth 1->0.9, depth 2->0.8, etc., min 0.5
            width_factor = max(0.5, 1.0 - (depth * 0.1))
            return int(absolute_width * width_factor)
        else:
            return absolute_width

    @classmethod
    def make_pretty_panel(
        cls,
        content: str | Any,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
        console_width: int | None = None,
    ) -> Panel:
        pretty = cls.make_pretty(content, inner_title=inner_title, depth=0)
        # When width is not specified, measure the content to determine optimal console width
        if width is None:
            # Create a console to measure the panel
            measure_console = Console(width=console_width)
            measurement = Measurement.get(measure_console, measure_console.options, pretty)
            # Use the maximum width that fits the content, with some buffer for panel border rendering
            width = measurement.maximum + 4
            # print(f"width: {width}")
        if console_width is not None:
            width = min(width, console_width)
        return cls.wrap_in_panel(pretty=pretty, title=title, subtitle=subtitle, border_style=border_style, width=width)

    @classmethod
    def wrap_in_panel(
        cls,
        pretty: PrettyPrintable,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
    ) -> Panel:
        return Panel(
            pretty,
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

    @classmethod
    def pretty_text(
        cls,
        pretty: PrettyPrintable,
        width: int = PRETTY_WIDTH_FOR_EXPORT,
    ) -> str:
        """Export a PrettyPrintable as plain ASCII text without styling.

        Args:
            pretty: The Rich renderable to convert
            width: Console width for text wrapping

        Returns:
            Plain text string representation
        """
        buf = StringIO()
        console = Console(record=True, file=buf, width=width, force_terminal=False)
        console.print(pretty)
        return console.export_text()

    @classmethod
    def pretty_html(
        cls,
        pretty: PrettyPrintable,
        width: int = PRETTY_WIDTH_FOR_EXPORT,
    ) -> str:
        buf = StringIO()
        console = Console(record=True, file=buf, width=width, force_terminal=False)
        console.print(pretty)
        return console.export_html(inline_styles=False, clear=False, theme=EXPORT_THEME)

    @classmethod
    def pretty_svg(cls, pretty: PrettyPrintable, width: int = PRETTY_WIDTH_FOR_EXPORT) -> str:
        buf = StringIO()
        console = Console(record=True, file=buf, width=width, force_terminal=False)
        console.print(pretty)
        return console.export_svg()

    @classmethod
    def make_pretty(cls, value: Any, inner_title: str | None = None, depth: int = 0) -> PrettyPrintable:
        pretty: PrettyPrintable
        # Format the value
        if isinstance(value, PrettyPrintable):
            pretty = value
        elif isinstance(value, PrettyRenderable):
            pretty = value.rendered_pretty(depth=depth)
        elif isinstance(value, BaseModel):
            # Wrap regular BaseModel to get truncated __rich_repr__ with proper class name
            pretty = Pretty(make_truncated_wrapper(value))
        elif isinstance(value, dict):
            # For dicts, apply truncation and use JSON rendering
            truncated_data = AttributePolisher.apply_truncation_recursive(value)
            try:
                pretty = JSON.from_data(truncated_data, indent=4)
            except TypeError:
                json_string = kajson.dumps(truncated_data, indent=4)
                pretty = Syntax(json_string, "json", theme="monokai")
        elif isinstance(value, list):
            # For lists, build a table without headers
            list_table = Table(
                show_header=False,
                show_edge=False,
                show_lines=True,
                border_style="dim",
                padding=(0, 1),
            )
            list_table.add_column("No.", style="yellow", justify="center", width=4)
            list_table.add_column("Item", style="white")

            for idx, item in enumerate(value, start=1):  # type: ignore[arg-type]
                pretty_item = cls.make_pretty(item, inner_title=None, depth=depth + 1)
                list_table.add_row(str(idx), pretty_item)

            pretty = list_table
        elif isinstance(value, str):
            # Handle URLs specially, otherwise use Text for simple strings
            if value.startswith(("http://", "https://")):
                pretty = Text(value, style="link " + value, no_wrap=True)
            elif AttributePolisher.should_truncate(value=value):
                # Truncate long base64-like strings
                pretty = Text(AttributePolisher.get_truncated_value(value))
            else:
                # Use Text instead of Markdown to allow proper auto-sizing
                pretty = Text(value)
        elif isinstance(value, (int, float, bool)):
            # For primitive types, convert to string
            pretty = Text(str(value))
        else:
            # For other types, use Rich's native Pretty rendering
            pretty = Pretty(value)

        if inner_title:
            inner_title_text = Text(str(inner_title), style="dim")
            pretty = Group(inner_title_text, pretty)

        return pretty

    @classmethod
    def pretty_print_without_rich(
        cls,
        content: str | Any,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        width: int | None = None,
        console_width: int | None = None,
    ):
        if isinstance(content, str) and content.startswith(("http://", "https://")):
            cls.pretty_print_url_without_rich(content=content, title=title, subtitle=subtitle)
            return
        title_str = str(title) if title else ""
        if subtitle:
            title_str += f"\n{subtitle!s}"
        if inner_title:
            title_str += f"\n{inner_title}"
        terminal_width = console_width or shutil.get_terminal_size().columns
        content_str = f"{content}"

        # Split title into lines if it contains newlines
        title_lines = title_str.splitlines() if title_str else []

        # Calculate max content width based on longest title line
        max_title_len = max(len(line) for line in title_lines) if title_lines else 0
        max_content_width = terminal_width - max_title_len - 8  # Accounting for frame and padding
        if width:
            max_content_width = min(max_content_width, width)
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

        print_to_stderr(f"{BORDER_COLOR}{top_border}{RESET_FONT}")
        # Print each title line separately
        for title_line in title_lines:
            padding = " " * (frame_width - len(title_line) - 4)
            print_to_stderr(f"{BORDER_COLOR}│ {BOLD_FONT}{TITLE_COLOR}{title_line}{RESET_FONT}:{padding}{BORDER_COLOR}│{RESET_FONT}")
        for line in wrapped_lines:
            padding = " " * (frame_width - len(line) - 3)
            print_to_stderr(f"{BORDER_COLOR}│ {TEXT_COLOR}{line}{RESET_FONT}{padding}{BORDER_COLOR}│{RESET_FONT}")
        print_to_stderr(f"{BORDER_COLOR}{bottom_border}{RESET_FONT}")

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

        print_to_stderr(f"{BORDER_COLOR}{top_border}{RESET_FONT}")
        if title:
            title_padding = " " * (frame_width - len(title) - 4)
            print_to_stderr(f"{BORDER_COLOR}│ {BOLD_FONT}{TITLE_COLOR}{title}{RESET_FONT}:{title_padding}{BORDER_COLOR}│{RESET_FONT}")
        print_to_stderr(f"{TEXT_COLOR}{content}{RESET_FONT}")
        print_to_stderr(f"{BORDER_COLOR}{bottom_border}{RESET_FONT}")
