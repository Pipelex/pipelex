"""The console layouts: Rich templates over a record's fields, for the few lines whose shape matters on a terminal.

A call names its layout with ``layout=`` (``log.info("Pipe run starts", fields={...}, layout=LogLayout.PIPE_RUN)``),
which the dispatch stamps on the record under ``LAYOUT_MARK`` when the call's content is a string, and drops
for any other content, which only the message renders. The ``console`` sink renders such a record
through the layout's template in place of its message, and every other sink ignores the layout and writes
the plain message and the fields: the mark is reserved, so it reaches no wire. The name is explicit at the
call, so rewording the message can never silently lose the layout.

A template is Rich markup with ``{name}`` placeholders. Each placeholder is a field of the record, or a value
the layout derives from the fields, such as an indentation computed from a depth. Every value is rendered on
one line and escaped with Rich's own escape before it is substituted, the derived ones included, so a value
can never be read as markup: a field carrying ``[red]`` prints as written. The fields a layout presents are
left out of the suffix that follows it; any other field the call gave still renders there. A layout whose
fields are missing, whose derivation refuses a value or whose template Rich refuses, costs nothing but
itself: whatever it raised, the console falls back to the message and the suffix. A traceback the record
carries prints under the line either way, and a record the redaction quarantined loses its layout, so the
notice saying why its fields are redacted is what prints.

The registry is one table in code. Rich is imported only where a layout is rendered, after asking for it.
"""

from __future__ import annotations

import math
import string
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, field_validator
from typing_extensions import override

from pipelex.system.telemetry.otel_constants import GenAISpanAttr
from pipelex.tools.log.console_fields import FIELD_STYLES, format_layout_value, one_line_text
from pipelex.tools.log.summary_fields import COST_USD_FIELD, DURATION_MS_FIELD, OUTCOME_FIELD, Outcome
from pipelex.tools.misc.rich_extra import require_rich

if TYPE_CHECKING:
    from collections.abc import Mapping

#: What a layout says when the extra is missing; only the console sink renders one, and it asked already.
CONSOLE_LAYOUT_MISSING_MESSAGE = "A console layout renders through Rich."


class LogLayout(StrEnum):
    """The layouts a log call can name with ``layout=``."""

    PIPE_RUN = "pipe_run"
    PIPE_RUN_END = "pipe_run_end"
    INFERENCE_CALL_END = "inference_call_end"


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

        A derivation is each layout's own code, so the errors below are what a well-behaved one raises rather
        than all it can: the console sink falls back to the message whatever a layout raises.

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
PIPE_RUN_BRANCH = "↳"
#: What separates the branch mark from the pipe type. It is a placeholder of its own, outside the mark's style, so
#: the line is the very one the announcement printed when it was written as markup in its message, colour codes
#: included.
PIPE_RUN_GAP = " "
#: The deepest nesting the pipe-run layout indents. The indentation is built from the depth, so an unbounded
#: one builds a string as long as the caller likes, or raises ``OverflowError``; a deeper run than this,
#: which is far past any pipe stack a run reaches, falls back to its message.
PIPE_RUN_MAX_DEPTH = 100


class PipeRunLayout(ConsoleLayout):
    """The pipe-run tree: a nested run indented under its parent, behind a branch mark.

    ``PipeCompose: compose_company → Company`` at the top level, the same line indented and behind ``↳`` for
    a nested run. It reads ``pipe_depth``, an integer from ``0`` for a top-level run up to
    ``PIPE_RUN_MAX_DEPTH``. Only a live run announces itself, so the layout draws no run mode.
    """

    @override
    def derived_values(self, *, fields: Mapping[str, Any]) -> dict[str, Any]:
        """The indentation and the branch mark, from a depth this layout checks first.

        Raises:
            TypeError: If the depth is not an integer.
            ValueError: If the depth is negative or deeper than ``PIPE_RUN_MAX_DEPTH``.
        """
        depth = fields["pipe_depth"]
        # A boolean is an integer to Python, and ``True`` would indent one level.
        if isinstance(depth, bool) or not isinstance(depth, int):
            msg = f"The pipe-run layout's depth must be an integer, not {type(depth).__name__}"
            raise TypeError(msg)
        if not 0 <= depth <= PIPE_RUN_MAX_DEPTH:
            msg = f"The pipe-run layout's depth must be between 0 and {PIPE_RUN_MAX_DEPTH}"
            raise ValueError(msg)
        is_nested = depth > 0
        return {
            "indent": PIPE_RUN_INDENT * depth,
            "branch": PIPE_RUN_BRANCH if is_nested else "",
            "branch_gap": PIPE_RUN_GAP if is_nested else "",
        }


PIPE_RUN_LAYOUT = PipeRunLayout(
    template=(
        "{indent}[yellow]{branch}[/yellow]{branch_gap}"
        f"{_styled_placeholder(field='pipe_type', suffix=':')} {_styled_placeholder(field='pipe_code')} "
        f"[yellow]→[/yellow] {_styled_placeholder(field='output_concept')}"
    ),
    presented_fields=frozenset({"pipe_type", "pipe_code", "output_concept", "pipe_depth"}),
)

#: What a summary event says before its duration, by how the work ended.
SUCCESS_ENDING = "done in"
ERROR_ENDING = "failed after"
CANCELLED_ENDING = "cancelled after"
#: Below this many milliseconds a duration is written in milliseconds, and in seconds from it on.
MILLISECONDS_PER_SECOND = 1000
#: How many decimals of a dollar a cost is written to, before its trailing zeros are dropped.
COST_DECIMALS = 6


def _endings(*, outcome: Any) -> dict[str, str]:
    """The success, error and cancelled endings of a summary event, all but one of them empty, so each takes its own style.

    Raises:
        ValueError: If the outcome is not one of ``success``, ``error`` and ``cancelled``.
    """
    match Outcome(outcome):
        case Outcome.SUCCESS:
            return {"success_ending": SUCCESS_ENDING, "error_ending": "", "cancelled_ending": ""}
        case Outcome.ERROR:
            return {"success_ending": "", "error_ending": ERROR_ENDING, "cancelled_ending": ""}
        case Outcome.CANCELLED:
            return {"success_ending": "", "error_ending": "", "cancelled_ending": CANCELLED_ENDING}


def _is_number(*, value: Any) -> bool:
    """Whether a value is a finite number, a boolean, which is an integer to Python, excluded."""
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def format_duration(*, duration_ms: Any) -> str:
    """A duration in milliseconds as a person reads it: ``840 ms`` under a second, ``1.25 s`` from a second on.

    Raises:
        TypeError: If the duration is not a number.
        ValueError: If the duration is negative or not finite.
    """
    if not _is_number(value=duration_ms):
        msg = f"A duration must be a finite number of milliseconds, not {type(duration_ms).__name__}"
        raise TypeError(msg)
    if duration_ms < 0:
        msg = "A duration cannot be negative"
        raise ValueError(msg)
    if round(duration_ms) < MILLISECONDS_PER_SECOND:
        return f"{duration_ms:.0f} ms"
    return f"{duration_ms / MILLISECONDS_PER_SECOND:.2f} s"


def format_cost(*, cost_usd: Any) -> str:
    """A cost in US dollars to the millionth of a dollar, its trailing zeros dropped: ``$0.0123``, ``$0``.

    Raises:
        TypeError: If the cost is not a number.
    """
    if not _is_number(value=cost_usd):
        msg = f"A cost must be a finite number of dollars, not {type(cost_usd).__name__}"
        raise TypeError(msg)
    return f"${cost_usd:.{COST_DECIMALS}f}".rstrip("0").rstrip(".")


def _format_token_count(*, nb_tokens: Any) -> str:
    """A token count with its thousands separated: ``12,288``.

    Raises:
        TypeError: If the count is not an integer.
    """
    if isinstance(nb_tokens, bool) or not isinstance(nb_tokens, int):
        msg = f"A token count must be an integer, not {type(nb_tokens).__name__}"
        raise TypeError(msg)
    return f"{nb_tokens:,}"


class PipeRunEndLayout(PipeRunLayout):
    """The end of a pipe run, drawn in the pipe tree under the line that announced it.

    ``PipeLLM: describe_company done in 1.25 s``, indented and behind ``↳`` at the depth of its announcement. It reads
    the pipe-run layout's depth, ``duration_ms`` and ``outcome``; a failure says ``failed after`` in red, and its
    ``error.type`` follows as the suffix, and a cancelled run says ``cancelled after`` in yellow.
    """

    @override
    def derived_values(self, *, fields: Mapping[str, Any]) -> dict[str, Any]:
        """The tree's indentation and branch mark, the ending the outcome calls for, and the duration as a person reads it.

        Raises:
            TypeError: If the depth or the duration is of the wrong type.
            ValueError: If the depth is out of range, the duration negative or the outcome unknown.
        """
        return {
            **super().derived_values(fields=fields),
            **_endings(outcome=fields[OUTCOME_FIELD]),
            "duration": format_duration(duration_ms=fields[DURATION_MS_FIELD]),
        }


PIPE_RUN_END_LAYOUT = PipeRunEndLayout(
    template=(
        "{indent}[yellow]{branch}[/yellow]{branch_gap}"
        f"{_styled_placeholder(field='pipe_type', suffix=':')} {_styled_placeholder(field='pipe_code')} "
        "[dim]{success_ending}[/dim][bold red]{error_ending}[/bold red][yellow]{cancelled_ending}[/yellow] {duration}"
    ),
    presented_fields=frozenset({"pipe_type", "pipe_code", "output_concept", "pipe_depth", DURATION_MS_FIELD, OUTCOME_FIELD}),
)


class InferenceCallEndLayout(ConsoleLayout):
    """The end of an inference call, on one compact line: the model, the operation, the tokens, the cost and the duration.

    ``claude-5.5-sonnet chat · 2,048 → 512 tokens · $0.009216 · done in 1.23 s``, the tokens in before the arrow and out
    after it. A count or a cost the call did not report is left out with its separator. The model is drawn by its
    handle, and the keys that name the same model otherwise, ``gen_ai.request.model``, ``gen_ai.response.model``,
    ``backend_name`` and ``sdk``, are left off the line, which the ``json`` sink writes in full. A failure says
    ``failed after`` in red, and its ``error.type`` follows as the suffix; a cancelled call says ``cancelled after`` in
    yellow.
    """

    @override
    def derived_values(self, *, fields: Mapping[str, Any]) -> dict[str, Any]:
        """The operation, the usage with its separators, the ending the outcome calls for and the duration.

        Raises:
            TypeError: If a token count, the cost or the duration is of the wrong type.
            ValueError: If the duration is negative or the outcome unknown.
        """
        input_tokens = fields.get(GenAISpanAttr.USAGE_INPUT_TOKENS)
        output_tokens = fields.get(GenAISpanAttr.USAGE_OUTPUT_TOKENS)
        usage_parts: list[str] = []
        if input_tokens is not None and output_tokens is not None:
            usage_parts.append(f"{_format_token_count(nb_tokens=input_tokens)} → {_format_token_count(nb_tokens=output_tokens)} tokens")
        elif input_tokens is not None:
            usage_parts.append(f"{_format_token_count(nb_tokens=input_tokens)} tokens in")
        elif output_tokens is not None:
            usage_parts.append(f"{_format_token_count(nb_tokens=output_tokens)} tokens out")
        cost_usd = fields.get(COST_USD_FIELD)
        if cost_usd is not None:
            usage_parts.append(format_cost(cost_usd=cost_usd))
        return {
            "operation": fields[GenAISpanAttr.OPERATION_NAME],
            "usage": "".join(f" · {part}" for part in usage_parts),
            **_endings(outcome=fields[OUTCOME_FIELD]),
            "duration": format_duration(duration_ms=fields[DURATION_MS_FIELD]),
        }


INFERENCE_CALL_END_LAYOUT = InferenceCallEndLayout(
    template=(
        "[cyan]{model_handle}[/cyan] [dim]{operation}[/dim]{usage} · "
        "[dim]{success_ending}[/dim][bold red]{error_ending}[/bold red][yellow]{cancelled_ending}[/yellow] {duration}"
    ),
    presented_fields=frozenset(
        {
            GenAISpanAttr.OPERATION_NAME,
            "model_handle",
            "backend_name",
            "sdk",
            GenAISpanAttr.REQUEST_MODEL,
            GenAISpanAttr.RESPONSE_MODEL,
            GenAISpanAttr.USAGE_INPUT_TOKENS,
            GenAISpanAttr.USAGE_OUTPUT_TOKENS,
            COST_USD_FIELD,
            DURATION_MS_FIELD,
            OUTCOME_FIELD,
        }
    ),
)

#: Every layout a call can name, by its name.
CONSOLE_LAYOUTS: dict[LogLayout, ConsoleLayout] = {
    LogLayout.PIPE_RUN: PIPE_RUN_LAYOUT,
    LogLayout.PIPE_RUN_END: PIPE_RUN_END_LAYOUT,
    LogLayout.INFERENCE_CALL_END: INFERENCE_CALL_END_LAYOUT,
}


def console_layout(*, name: str) -> ConsoleLayout | None:
    """The layout registered under the name, or ``None`` for a name no layout has."""
    try:
        layout_name = LogLayout(name)
    except ValueError:
        return None
    return CONSOLE_LAYOUTS.get(layout_name)
