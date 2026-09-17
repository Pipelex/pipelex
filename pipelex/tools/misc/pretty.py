"""The pretty-print engine: the mode, the Rich panels, and the plain-text panels printed without Rich.

Rich is the ``cli`` extra, so this module imports it nowhere at module level: each method of the ``rich``
mode, and each ``rendered_pretty`` on the model types, checks that Rich is installed and imports what it
renders with, inside its body. The ``poor`` mode frames plain text itself and never imports Rich; the
``silent`` mode builds nothing. A process without Rich renders in ``poor`` or ``silent`` and never loads
it, and one that asks for ``rich`` without it is refused at boot, naming the extra.
"""

from __future__ import annotations

import re
import shutil
import sys
from abc import ABC, abstractmethod
from enum import StrEnum
from io import StringIO
from typing import TYPE_CHECKING, Any, ClassVar

from kajson import kajson
from pydantic import BaseModel

from pipelex.tools.misc.attribute_utils import AttributePolisher
from pipelex.tools.misc.rich_extra import require_rich
from pipelex.tools.misc.terminal_utils import BOLD_FONT, RESET_FONT, TerminalColor, print_to_stderr
from pipelex.tools.typing.pydantic_utils import make_truncated_wrapper

if TYPE_CHECKING:
    from typing import TypeAlias

    from rich.console import Group
    from rich.json import JSON
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.pretty import Pretty
    from rich.style import StyleType
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text, TextType

    # The renderables a ``rendered_pretty`` returns and the ``rich`` mode prints as they are.
    PrettyPrintable: TypeAlias = Markdown | Text | JSON | Table | Group | Syntax | Pretty

TEXT_COLOR = TerminalColor.WHITE
TITLE_COLOR = TerminalColor.CYAN
BORDER_COLOR = TerminalColor.YELLOW

# TODO: Make PrettyPrinter a manager so we can init it with a proper config
PRETTY_WIDTH_MIN: int = 125
PRETTY_WIDTH_FOR_EXPORT: int = 100
MAX_RENDER_DEPTH = 6

RICH_RENDERING_MISSING_MESSAGE = (
    'The pretty-print mode "rich" and the rendered_pretty renderings print through Rich. Install the extra, '
    'or set pretty_print_mode to "poor" or "silent" in [runtime.log] for a process with no terminal: both render without it.'
)

# Rich's own console-markup tag pattern, ``rich.markup.RE_TAGS``: a run of backslashes, then a bracketed tag
# whose name starts with a lowercase letter, ``#``, ``/`` or ``@``.
_MARKUP_TAG_PATTERN = re.compile(r"((\\*)\[([a-z#/@][^[]*?)])")


def require_rich_for_rendering() -> None:
    """Raise ``MissingDependencyError`` naming the ``cli`` extra and the Rich-free modes when Rich is not installed.

    A ``rendered_pretty`` implementation calls it first, then imports what it renders with.
    """
    require_rich(message=RICH_RENDERING_MISSING_MESSAGE)


def _normalized_tag_name(*, name: str) -> str:
    """A tag name as an opening and a closing tag are matched on: case, spacing and word order aside, as Rich's style normalization does."""
    return " ".join(sorted(name.lower().split()))


def plain_markup_text(*, markup: str) -> str | None:
    """The text Rich console markup renders to, tags dropped, or ``None`` where Rich would refuse the markup.

    Rich-free, so the ``poor`` mode reads a title the way the Rich panel would without importing Rich. It
    follows ``rich.markup.render`` for what a title spells: tags, backslash-escaped brackets, and a closing
    tag that must close an open one, which is the markup Rich refuses. Emoji codes and style aliases are
    left as they are written.
    """
    if "[" not in markup:
        return markup
    pieces: list[str] = []
    open_tags: list[str] = []
    position = 0
    for match in _MARKUP_TAG_PATTERN.finditer(markup):
        full_text, escapes, tag_text = match.groups()
        start, end = match.span()
        if start > position:
            pieces.append(markup[position:start].replace("\\[", "["))
        position = end
        backslashes, escaped = divmod(len(escapes), 2)
        pieces.append("\\" * backslashes)
        if escaped:
            pieces.append(full_text[len(escapes) :])
            continue
        tag_name = tag_text.partition("=")[0]
        if not tag_name.startswith("/"):
            open_tags.append(_normalized_tag_name(name=tag_name))
            continue
        closed_name = _normalized_tag_name(name=tag_name[1:])
        if not closed_name:
            if not open_tags:
                return None
            open_tags.pop()
            continue
        if closed_name not in open_tags:
            return None
        del open_tags[len(open_tags) - 1 - open_tags[::-1].index(closed_name)]
    if position < len(markup):
        pieces.append(markup[position:].replace("\\[", "["))
    return "".join(pieces)


class PrettyRenderable(ABC):
    @abstractmethod
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        """A Rich renderable of this object, for the console.

        Rich is the ``cli`` extra: an implementation calls ``require_rich_for_rendering()`` and then imports
        what it renders with, inside the method.
        """

    def rendered_pretty_text(self, *, title: str | None = None, width: int = PRETTY_WIDTH_FOR_EXPORT) -> str:
        """Render as plain ASCII text string.

        Args:
            title: Optional title for the rendering
            width: Console width for text wrapping

        Returns:
            Plain text string representation

        Raises:
            MissingDependencyError: If Rich is not installed.
        """
        pretty = self.rendered_pretty(title=title, depth=0)
        return PrettyPrinter.pretty_text(pretty, width=width)


class PrettyPrintMode(StrEnum):
    RICH = "rich"
    POOR = "poor"
    SILENT = "silent"


def pretty_print(
    content: str | Any,
    *,
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
    *,
    title: TextType | None = None,
    subtitle: TextType | None = None,
    inner_title: str | None = None,
    border_style: StyleType | None = None,
    width: int | None = None,
    console_width: int | None = None,
):
    if PrettyPrinter.mode is PrettyPrintMode.SILENT:
        # A silent printer builds no renderable, and does not measure the terminal to size one.
        return
    width = width or PrettyPrinter.pretty_width()
    if PrettyPrinter.mode is PrettyPrintMode.POOR:
        # The poor printer renders no Markdown: it frames the source it was given.
        PrettyPrinter.pretty_print_without_rich(
            content, title=title, subtitle=subtitle, inner_title=inner_title, width=width, console_width=console_width
        )
        return
    require_rich_for_rendering()
    from rich.markdown import Markdown

    PrettyPrinter.pretty_print_using_rich(
        Markdown(content),
        title=title,
        subtitle=subtitle,
        inner_title=inner_title,
        border_style=border_style,
        width=width,
        console_width=console_width,
    )


def pretty_print_url(
    url: str,
    *,
    title: TextType | None = None,
    subtitle: TextType | None = None,
    inner_title: str | None = None,
    border_style: StyleType | None = None,
    width: int | None = None,
    console_width: int | None = None,
):
    if PrettyPrinter.mode is PrettyPrintMode.SILENT:
        # A silent printer builds no renderable.
        return
    if url.startswith("/"):
        url = "file://" + url
    if PrettyPrinter.mode is PrettyPrintMode.POOR:
        # The url on a row of its own, so a terminal can linkify it whole.
        PrettyPrinter.pretty_print_url_without_rich(url, title=title, subtitle=subtitle, width=width, console_width=console_width)
        return
    require_rich_for_rendering()
    from rich.text import Text

    PrettyPrinter.pretty_print_using_rich(
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
        *,
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
                cls.pretty_print_without_rich(
                    content=content, title=title, subtitle=subtitle, inner_title=inner_title, width=width, console_width=console_width
                )
            case PrettyPrintMode.SILENT:
                return

    @classmethod
    def pretty_print_using_rich(
        cls,
        content: str | Any,
        *,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
        console_width: int | None = None,
    ):
        """Print the content in a Rich panel on stdout, between two blank lines.

        Raises:
            MissingDependencyError: If Rich is not installed.
        """
        panel = cls.make_pretty_panel(
            content=content,
            title=title,
            subtitle=subtitle,
            inner_title=inner_title,
            border_style=border_style,
            width=width,
            console_width=console_width,
        )
        from rich.console import Console

        Console(width=console_width).print("", panel, "", sep="\n")

    @classmethod
    def pretty_width(cls, *, width: int | None = None, depth: int | None = None) -> int:
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
        *,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
        console_width: int | None = None,
    ) -> Panel:
        """The Rich panel the ``rich`` mode prints.

        Raises:
            MissingDependencyError: If Rich is not installed.
        """
        pretty = cls.make_pretty(content, inner_title=inner_title, depth=0)
        # When width is not specified, measure the content to determine optimal console width
        if width is None:
            from rich.console import Console
            from rich.measure import Measurement

            # Create a console to measure the panel
            measure_console = Console(width=console_width)
            measurement = Measurement.get(measure_console, measure_console.options, pretty)
            # Use the maximum width that fits the content, with some buffer for panel border rendering
            width = measurement.maximum + 4
        if console_width is not None:
            width = min(width, console_width)
        return cls.wrap_in_panel(pretty=pretty, title=title, subtitle=subtitle, border_style=border_style, width=width)

    @classmethod
    def wrap_in_panel(
        cls,
        pretty: PrettyPrintable,
        *,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        border_style: StyleType | None = None,
        width: int | None = None,
    ) -> Panel:
        """Raises MissingDependencyError if Rich is not installed."""
        require_rich_for_rendering()
        from rich.panel import Panel

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
        *,
        width: int = PRETTY_WIDTH_FOR_EXPORT,
    ) -> str:
        """Export a PrettyPrintable as plain ASCII text without styling.

        Args:
            pretty: The Rich renderable to convert
            width: Console width for text wrapping

        Returns:
            Plain text string representation

        Raises:
            MissingDependencyError: If Rich is not installed.
        """
        require_rich_for_rendering()
        from rich.console import Console

        buf = StringIO()
        console = Console(record=True, file=buf, width=width, force_terminal=False)
        console.print(pretty)
        return console.export_text()

    @classmethod
    def pretty_svg(cls, pretty: PrettyPrintable, *, width: int = PRETTY_WIDTH_FOR_EXPORT) -> str:
        """Raises MissingDependencyError if Rich is not installed."""
        require_rich_for_rendering()
        from rich.console import Console

        buf = StringIO()
        console = Console(record=True, file=buf, width=width, force_terminal=False)
        console.print(pretty)
        return console.export_svg()

    @classmethod
    def make_pretty(cls, value: Any, *, inner_title: str | None = None, depth: int = 0) -> PrettyPrintable:
        """The Rich renderable for any value: a renderable as it is, a ``PrettyRenderable`` rendered, anything else by its type.

        Raises:
            MissingDependencyError: If Rich is not installed.
        """
        require_rich_for_rendering()
        from rich.console import Group
        from rich.json import JSON
        from rich.markdown import Markdown
        from rich.pretty import Pretty
        from rich.syntax import Syntax
        from rich.table import Table
        from rich.text import Text

        pretty: PrettyPrintable
        # Format the value
        if isinstance(value, (Markdown, Text, JSON, Table, Group, Syntax, Pretty)):
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
        *,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        inner_title: str | None = None,
        width: int | None = None,
        console_width: int | None = None,
    ):
        if isinstance(content, str) and content.startswith(("http://", "https://")):
            cls.pretty_print_url_without_rich(content=content, title=title, subtitle=subtitle, width=width, console_width=console_width)
            return
        # Titles are Rich markup in every mode (a caller writes them once, for the Rich panel), so they are
        # measured and printed as the text they render to, not as the tags they are spelled with.
        title_str = cls._plain_title(title=title) if title else ""
        if subtitle:
            title_str += f"\n{cls._plain_title(title=subtitle)}"
        if inner_title:
            title_str += f"\n{inner_title}"
        terminal_width = console_width or shutil.get_terminal_size().columns

        # Split title into lines if it contains newlines
        title_lines = title_str.splitlines() if title_str else []

        # Titles sit on rows of their own, so they take nothing from the content's width. The width is
        # floored at one character, the smallest step the wrapping below can take through a line.
        max_content_width = terminal_width - 8  # Accounting for frame and padding
        if width:
            max_content_width = min(max_content_width, width)
        max_content_width = max(max_content_width, 1)
        # A title never widens the frame past the terminal: it is elided to the width the content wraps to, the way
        # Rich's `Panel` truncates an over-wide title, rather than spilling the box it is supposed to sit inside.
        title_lines = [cls._elide(line=line, max_width=max_content_width) for line in title_lines]
        # A caller handing over a Rich renderable gets its text, not the object's repr.
        renderable_text = cls._rich_renderable_text(content=content, width=max_content_width)
        content_str = f"{content}" if renderable_text is None else renderable_text
        wrapped_lines: list[str] = []
        for line in content_str.splitlines():
            if not line:
                wrapped_lines.append(line)
            for index_start in range(0, len(line), max_content_width):
                wrapped_lines.append(line[index_start : index_start + max_content_width])

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
    def _rich_renderable_text(cls, *, content: Any, width: int) -> str | None:
        """The text of a Rich renderable handed to the poor printer, or ``None`` for any other content.

        A Rich object exists only once Rich is imported, so a process that has not imported Rich holds none
        to hand over, and the check costs it no import.
        """
        if "rich" not in sys.modules:
            return None
        from rich.console import Group
        from rich.json import JSON
        from rich.markdown import Markdown
        from rich.pretty import Pretty
        from rich.syntax import Syntax
        from rich.table import Table
        from rich.text import Text

        if not isinstance(content, (Markdown, Text, JSON, Table, Group, Syntax, Pretty)):
            return None
        return cls.pretty_text(content, width=width)

    @classmethod
    def _plain_title(cls, *, title: TextType) -> str:
        """The text a panel title renders to: markup tags dropped, as Rich's `Panel` would drop them."""
        if not isinstance(title, str):
            # A Rich `Text`, which exists only where Rich is imported.
            return title.plain
        plain = plain_markup_text(markup=title)
        # A title spelling something Rich reads as an unmatched closing tag — a path in brackets, say — is
        # printed as it stands. The poor mode is the one that prints whatever happens, so it never raises here.
        return title if plain is None else plain

    @classmethod
    def _elide(cls, *, line: str, max_width: int) -> str:
        """The line cut to `max_width`, ending in an ellipsis when anything was cut."""
        if len(line) <= max_width:
            return line
        if max_width <= 1:
            return line[:max_width]
        return line[: max_width - 1] + "…"

    @classmethod
    def pretty_print_url_without_rich(
        cls,
        content: str | Any,
        *,
        title: TextType | None = None,
        subtitle: TextType | None = None,
        width: int | None = None,
        console_width: int | None = None,
    ):
        # The url itself prints on a row of its own, outside the frame, so a terminal can linkify it whole.
        # Everything around it obeys the same rules as the framed printer: markup titles render to their text,
        # and nothing is drawn wider than the terminal.
        title_str = cls._plain_title(title=title) if title else ""
        if subtitle:
            title_str += f" ({cls._plain_title(title=subtitle)})"
        terminal_width = console_width or shutil.get_terminal_size().columns
        frame_width = terminal_width - 2
        if width:
            frame_width = min(frame_width, width + 6)
        frame_width = max(frame_width, 5)
        title_str = cls._elide(line=title_str, max_width=frame_width - 4)
        top_border = "╭" + "─" * (frame_width - 2) + "╮"
        bottom_border = "╰" + "─" * (frame_width - 2) + "╯"

        print_to_stderr(f"{BORDER_COLOR}{top_border}{RESET_FONT}")
        if title_str:
            title_padding = " " * (frame_width - len(title_str) - 4)
            print_to_stderr(f"{BORDER_COLOR}│ {BOLD_FONT}{TITLE_COLOR}{title_str}{RESET_FONT}:{title_padding}{BORDER_COLOR}│{RESET_FONT}")
        print_to_stderr(f"{TEXT_COLOR}{content}{RESET_FONT}")
        print_to_stderr(f"{BORDER_COLOR}{bottom_border}{RESET_FONT}")
