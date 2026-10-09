"""The console layouts: Rich templates over a record's fields, for the few lines whose shape matters on a terminal.

A call names its layout with ``layout=`` (``log.info("Pipe run starts", fields={...}, layout=LogLayout.PIPE_RUN)``),
which the dispatch stamps on the record under ``LAYOUT_MARK``. The ``console`` sink renders such a record
through the layout's template in place of its message, and every other sink ignores the layout and writes
the plain message and the fields: the mark is reserved, so it reaches no wire. The name is explicit at the
call, so rewording the message can never silently lose the layout.

A template is Rich markup with ``{name}`` placeholders. Each placeholder is a field of the record, or a value
the layout derives from the fields, such as an indentation computed from a depth. Every value is rendered on
one line and escaped with Rich's own escape before it is substituted, the derived ones included, so a value
can never be read as markup: a field carrying ``[red]`` prints as written. The fields a layout presents are
left out of the suffix that follows it; any other field the call gave still renders there. A layout whose
fields are missing, or whose template Rich refuses, costs nothing but itself: the console falls back to the
message and the suffix. A record carrying structured content falls back the same way, since only its message
renders that content. A traceback the record carries prints under the line either way.

The registry is one table in code. Rich is imported only where a layout is rendered, after asking for it.
"""

from __future__ import annotations

import string
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, field_validator
from typing_extensions import override

from pipelex.tools.log.console_fields import FIELD_STYLES, format_layout_value, one_line_text
from pipelex.tools.misc.rich_extra import require_rich

if TYPE_CHECKING:
    from collections.abc import Mapping

#: What a layout says when the extra is missing; only the console sink renders one, and it asked already.
CONSOLE_LAYOUT_MISSING_MESSAGE = "A console layout renders through Rich."


class LogLayout(StrEnum):
    """The layouts a log call can name with ``layout=``."""

    PIPE_RUN = "pipe_run"


class ConsoleLayout(BaseModel):
    """A Rich template over a record's fields, and the fields it presents.

    ``template`` is Rich markup with ``{name}`` placeholders, and nothing but a bare name in a placeholder.
    ``presented_fields`` are the record's fields the layout shows, which the suffix after it does not
    repeat; they are the placeholders that name a field and those ``derived_values`` reads. A subclass
    overrides ``derived_values`` to compute presentation values from the fields, which are escaped like the
    fields themselves.
    """

    model_config = ConfigDict(frozen=True)

    template: str
    presented_fields: frozenset[str]

    @field_validator("template")
    @classmethod
    def validate_template(cls, template: str) -> str:
        for _, placeholder, format_spec, conversion in string.Formatter().parse(template):
            if placeholder is None:
                continue
            if not placeholder.isidentifier() or format_spec or conversion:
                msg = f"A console layout's placeholder must be a bare name, with no attribute, index, format spec or conversion: '{{{placeholder}}}'"
                raise ValueError(msg)
        return template

    @property
    def placeholders(self) -> tuple[str, ...]:
        """The names the template substitutes, in order of first appearance."""
        names: dict[str, None] = {}
        for _, placeholder, _, _ in string.Formatter().parse(self.template):
            if placeholder is not None:
                names[placeholder] = None
        return tuple(names)

    def derived_values(self, *, fields: Mapping[str, Any]) -> dict[str, Any]:
        """Presentation values the template substitutes beside the fields. None by default."""
        del fields
        return {}

    def render_markup(self, *, fields: Mapping[str, Any]) -> str:
        """The template filled with the fields and the derived values, each on one line and escaped.

        Raises:
            KeyError: If a placeholder names neither a field of the record nor a derived value.
            ValueError: If a derivation refuses a field's value.
            TypeError: If a derivation refuses a field's type.
        """
        require_rich(message=CONSOLE_LAYOUT_MISSING_MESSAGE)
        from rich.markup import escape

        derived = self.derived_values(fields=fields)
        substitutions: dict[str, str] = {}
        for name in self.placeholders:
            if name in derived:
                text = one_line_text(text=str(derived[name]))
            else:
                text = format_layout_value(value=fields[name])
            substitutions[name] = escape(text)
        return self.template.format_map(substitutions)


def _styled_placeholder(*, field: str, suffix: str = "") -> str:
    """A field's placeholder in the style ``FIELD_STYLES`` gives it, so a layout and the suffix colour it alike."""
    return f"[{FIELD_STYLES[field]}]{{{field}}}{suffix}[/]"


#: How far a nested pipe run is indented per level of depth.
PIPE_RUN_INDENT = "   "
#: What marks a nested pipe run, after its indentation.
PIPE_RUN_BRANCH = "↳ "
#: What precedes a dry run's pipe type.
PIPE_RUN_DRY_RUN_LABEL = "Dry run: "


class PipeRunLayout(ConsoleLayout):
    """The pipe-run tree: a nested run indented under its parent, behind a branch mark, a dry run labelled.

    ``PipeCompose: compose_company → Company`` at the top level, the same line indented and behind ``↳`` for
    a nested run, ``Dry run:`` before the pipe type for a dry one. It reads ``pipe_depth``, ``0`` for a
    top-level run, and ``is_dry_run``.
    """

    @override
    def derived_values(self, *, fields: Mapping[str, Any]) -> dict[str, Any]:
        # A depth that is not an integer makes the repetition raise ``TypeError``, which is the fallback's cue.
        depth = fields["pipe_depth"]
        return {
            "indent": PIPE_RUN_INDENT * depth,
            "branch": PIPE_RUN_BRANCH if depth > 0 else "",
            "dry_run_label": PIPE_RUN_DRY_RUN_LABEL if fields["is_dry_run"] else "",
        }


PIPE_RUN_LAYOUT = PipeRunLayout(
    template=(
        "{indent}[yellow]{branch}[/yellow][dim]{dry_run_label}[/dim]"
        f"{_styled_placeholder(field='pipe_type', suffix=':')} {_styled_placeholder(field='pipe_code')} "
        f"[yellow]→[/yellow] {_styled_placeholder(field='output_concept')}"
    ),
    presented_fields=frozenset({"pipe_type", "pipe_code", "output_concept", "pipe_depth", "is_dry_run"}),
)

#: Every layout a call can name, by its name.
CONSOLE_LAYOUTS: dict[LogLayout, ConsoleLayout] = {
    LogLayout.PIPE_RUN: PIPE_RUN_LAYOUT,
}


def console_layout(*, name: str) -> ConsoleLayout | None:
    """The layout registered under the name, or ``None`` for a name no layout has."""
    try:
        layout_name = LogLayout(name)
    except ValueError:
        return None
    return CONSOLE_LAYOUTS.get(layout_name)
