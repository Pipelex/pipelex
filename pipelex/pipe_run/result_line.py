"""The result line of a finished run: one line wording what it produced (spec: manifest-format.md, "Result Line").

A method's manifest may word that line with a `result_line` template over the output of its `main_pipe`; the library
load puts the template on that pipe (`PipeAbstract.result_line`). When a run ends with a value, the runtime renders the
template once against the main output, as a stuff carries it on the wire, and keeps the line with the run's output. When
there is no template, or it renders empty or fails, the line is derived from the output's `verdict` enumeration field.
A result line never fails a run: a run that has neither a line nor a derived one simply has none.

The template reads each object of the output as a `WireRecord`, whose fields win over the names a Python dict answers
with, so `{{ output.items }}` reads a field named `items`, as the line reads in every engine.
"""

import json
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from typing import Any, cast

from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.choice_options import ChoiceOptionTable, ChoiceOptionValue
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptLibraryConceptNotFoundError
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.exceptions import WorkingMemoryStuffNotFoundError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import get_required_concept
from pipelex.language.intent_hints import PART_HINT_KEY, PartWord
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.tools.jinja2.exceptions import (
    Jinja2ContextError,
    Jinja2StuffError,
    Jinja2TemplateBudgetError,
    Jinja2TemplateRenderError,
    Jinja2TemplateSecurityError,
    Jinja2TemplateSyntaxError,
)
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_async
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.jinja2.template_owner import TemplateOwner
from pipelex.tools.jinja2.template_surface import TemplateSurface
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.misc.json_utils import clean_json_dumps

RESULT_LINE_VARIABLE = "output"
"""The one variable a result line reads."""

_WHITE_SPACE_RUN = re.compile(r"\s+")

COUNT_SEPARATOR = " · "
"""What joins the counts of a derived line: a space, a middle dot and a space."""


def wire_output_content(*, content: StuffContent) -> Any:
    """The output's content as a stuff carries it on the wire: an object for a single value, an array for a plural one.

    A stored value is its reference, as on the wire.

    Raises:
        TypeError: A value of the content has no JSON form.
        ValueError: The content holds itself, which no JSON form can.
    """
    dumped: Any = json.loads(clean_json_dumps(content.smart_dump()))
    if isinstance(content, ListContent) and isinstance(dumped, dict):
        dumped_list = cast("dict[str, Any]", dumped)
        return dumped_list.get("items", dumped_list)
    return dumped


def as_template_value(*, value: Any) -> Any:
    """A wire value as a result line reads it: each object a `WireRecord`, each array a list of such values."""
    if isinstance(value, dict):
        return WireRecord(fields=cast("dict[str, Any]", value))
    if isinstance(value, list):
        return [as_template_value(value=item) for item in cast("list[Any]", value)]
    return value


class WireRecord:
    """An object of the wire as a result line's template reads it: its fields first, whatever their names.

    Jinja2 reads `record.name` as an attribute before an item, so on a Python dict a field named `items`, `values`,
    `keys`, `get` or `update` would read as the dict's method, or be refused by the sandbox as one that changes the
    dict. Here a field always wins: `{{ output.items }}` reads the field `items`. Without a field of that name, `get`,
    `items`, `keys` and `values` are the methods a template may call, as on a dict. Printed, the record is the plain
    object it wraps, as the dict printed before.
    """

    __slots__ = ("_fields",)
    _fields: dict[str, Any]

    __template_surface__ = TemplateSurface(callable_names=frozenset({"get", "items", "keys", "values"}), private_names=frozenset())

    def __init__(self, *, fields: dict[str, Any]) -> None:
        object.__setattr__(self, "_fields", fields)

    @override
    def __getattribute__(self, key: str) -> Any:
        if not key.startswith("_"):
            fields: dict[str, Any] = object.__getattribute__(self, "_fields")
            if key in fields:
                return as_template_value(value=fields[key])
        return object.__getattribute__(self, key)

    def __getitem__(self, key: str) -> Any:
        return as_template_value(value=self._fields[key])

    def __contains__(self, key: object) -> bool:
        return key in self._fields

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    @override
    def __eq__(self, other: object) -> bool:
        if isinstance(other, WireRecord):
            return self._fields == other._fields
        return self._fields == other

    @override
    def __hash__(self) -> int:
        # Mutable like the dict it wraps, so unhashable like it.
        msg = f"unhashable type: '{type(self).__name__}'"
        raise TypeError(msg)

    @override
    def __str__(self) -> str:
        return str(self._fields)

    @override
    def __repr__(self) -> str:
        return repr(self._fields)

    def get(self, key: str, default: Any = None) -> Any:  # kw-only: ignore (a template calls it as a dict's get)
        """The field `key`, or `default` when the record has none."""
        return as_template_value(value=self._fields[key]) if key in self._fields else default

    def items(self) -> list[tuple[str, Any]]:
        """The record's fields and their values, in order."""
        return [(key, as_template_value(value=value)) for key, value in self._fields.items()]

    def keys(self) -> list[str]:
        """The record's field names, in order."""
        return list(self._fields)

    def values(self) -> list[Any]:
        """The record's field values, in order."""
        return [as_template_value(value=value) for value in self._fields.values()]


def collapse_line(*, rendered: str) -> str:
    """The rendered text as one line: each run of white space a single space, trimmed at both ends."""
    return _WHITE_SPACE_RUN.sub(" ", rendered).strip()


async def render_result_line(*, result_line: str, content: StuffContent, pipe_code: str) -> str | None:
    """The authored line, rendered against the output and collapsed, or None, with a warning, when it fails or leaves nothing.

    Every way the line can fail is caught, since a result line never fails a run: an output with no JSON form (a
    `TypeError` or a `ValueError`), the template's own faults, a filter or a method refusing this run's value, a refusal
    of the sandbox, which is warned and never rendered past, and a render past its budget.
    """
    try:
        output = as_template_value(value=wire_output_content(content=content))
        rendered = await render_jinja2_async(
            result_line,
            template_category=TemplateCategory.BASIC,
            templating_context={RESULT_LINE_VARIABLE: output},
            is_undefined_strict=True,
            template_owner=TemplateOwner.METHOD,
        )
    except (
        Jinja2TemplateSyntaxError,
        Jinja2TemplateRenderError,
        Jinja2StuffError,
        Jinja2ContextError,
        Jinja2TemplateBudgetError,
        Jinja2TemplateSecurityError,
        TypeError,
        ValueError,
    ) as exc:
        log.warning("A result line failed to render, so the line is derived", fields={"pipe_code": pipe_code, **error_fields(exc=exc)})
        return None
    return collapse_line(rendered=rendered) or None


def _marks_verdict(*, hints: dict[str, str] | None) -> bool:
    """Whether a field's hints give it the `verdict` part."""
    word = (hints or {}).get(PART_HINT_KEY)
    if word is None:
        return False
    try:
        part = PartWord(word)
    except ValueError:
        return False
    match part:
        case PartWord.VERDICT:
            return True
        case PartWord.TITLE | PartWord.SUMMARY | PartWord.METRIC | PartWord.BODY | PartWord.EVIDENCE | PartWord.DETAIL:
            return False


def _verdict_field(*, concept: Concept) -> tuple[str, list[ChoiceOptionValue]] | None:
    """The first field, in declared order, that the concept marks with the `verdict` part and that is an enumeration."""
    for field_name, field in (concept.declared_structure or {}).items():
        if field.choices and _marks_verdict(hints=field.hints):
            return field_name, field.choices
    return None


def _option_word(*, options: Sequence[ChoiceOptionValue], value: str) -> str:
    """The label of the option holding `value`, or the value itself when that option has no label."""
    for option in options:
        if isinstance(option, ChoiceOptionTable) and option.value == value and option.label:
            return option.label
    return value


def _counted_line(*, records: Sequence[StuffContent], field_name: str, options: Sequence[ChoiceOptionValue]) -> str | None:
    """The counts of the records by their verdict, in declared option order, each `<count> <label or value>`."""
    counts: Counter[str] = Counter()
    for record in records:
        value = getattr(record, field_name, None)
        if isinstance(value, str):
            counts[value] += 1
    parts: list[str] = []
    seen_values: set[str] = set()
    for option in options:
        value = option if isinstance(option, str) else option.value
        if value in seen_values or not counts[value]:
            continue
        seen_values.add(value)
        parts.append(f"{counts[value]} {_option_word(options=options, value=value)}")
    return COUNT_SEPARATOR.join(parts) or None


def _list_field_of_verdict_records(*, concept: Concept) -> tuple[str, str, list[ChoiceOptionValue]] | None:
    """The one `list` field whose items are records with a verdict field, with that field and its options, else None."""
    found: list[tuple[str, str, list[ChoiceOptionValue]]] = []
    for field_name, field in (concept.declared_structure or {}).items():
        item_concept = _list_item_concept(field=field, domain_code=concept.domain_code)
        if item_concept is None:
            continue
        verdict = _verdict_field(concept=item_concept)
        if verdict is not None:
            found.append((field_name, verdict[0], verdict[1]))
    return found[0] if len(found) == 1 else None


def _list_item_concept(*, field: ConceptStructureBlueprint, domain_code: str) -> Concept | None:
    """The concept of a `list` field's items, its bare code read in the domain of the concept declaring the field."""
    match field.type:
        case ConceptStructureBlueprintFieldType.LIST:
            if field.item_concept_ref is None:
                return None
            item_ref = field.item_concept_ref if "." in field.item_concept_ref else f"{domain_code}.{field.item_concept_ref}"
            try:
                return get_required_concept(item_ref)
            except (ConceptLibraryError, ConceptLibraryConceptNotFoundError):
                return None
        case (
            ConceptStructureBlueprintFieldType.TEXT
            | ConceptStructureBlueprintFieldType.INTEGER
            | ConceptStructureBlueprintFieldType.NUMBER
            | ConceptStructureBlueprintFieldType.BOOLEAN
            | ConceptStructureBlueprintFieldType.DATE
            | ConceptStructureBlueprintFieldType.DATETIME
            | ConceptStructureBlueprintFieldType.TIME
            | ConceptStructureBlueprintFieldType.DICT
            | ConceptStructureBlueprintFieldType.CONCEPT
            | None
        ):
            return None


def derive_result_line(*, stuff: Stuff) -> str | None:
    """The line derived from the output's `verdict` enumeration field, or None when the output has none to count."""
    content = stuff.content
    concept = stuff.concept
    verdict = _verdict_field(concept=concept)
    if isinstance(content, ListContent):
        if verdict is None:
            return None
        items: list[StuffContent] = list(content.items)  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
        return _counted_line(records=items, field_name=verdict[0], options=verdict[1])
    if not isinstance(content, StructuredContent):
        return None
    if verdict is not None:
        value = getattr(content, verdict[0], None)
        return _option_word(options=verdict[1], value=value) if isinstance(value, str) else None
    listed = _list_field_of_verdict_records(concept=concept)
    if listed is None:
        return None
    list_field_name, field_name, options = listed
    records: Any = getattr(content, list_field_name, None)
    if not isinstance(records, list):
        return None
    record_list = cast("list[Any]", records)
    return _counted_line(records=[record for record in record_list if isinstance(record, StuffContent)], field_name=field_name, options=options)


async def result_line_of_run(*, result_line: str | None, pipe_output: PipeOutput, pipe_code: str) -> str | None:
    """The result line of a run that ended with `pipe_output`: the authored line, else the derived one, else None.

    A run whose output resolved absent has no line, and so has one whose working memory holds no main output, with a
    warning: the run's own result is reported as it is, since a result line never fails a run.
    """
    try:
        main_stuff = pipe_output.working_memory.resolve_main_stuff()
    except WorkingMemoryStuffNotFoundError as exc:
        log.warning("A run ended with no main output, so it has no result line", fields={"pipe_code": pipe_code, **error_fields(exc=exc)})
        return None
    if isinstance(main_stuff, AbsenceRecord):
        return None
    if result_line is not None:
        authored = await render_result_line(result_line=result_line, content=main_stuff.content, pipe_code=pipe_code)
        if authored is not None:
            return authored
    return derive_result_line(stuff=main_stuff)
