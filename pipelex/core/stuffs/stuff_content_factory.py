import datetime
import re
from typing import Any

from pipelex.core.concepts.concept import Concept
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.exceptions import StuffContentFactoryError
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.runtime_hub import get_class_registry


class StuffContentFactory:
    @classmethod
    def make_content_from_value(
        cls, *, stuff_content_subclass: type[StuffContent], value: dict[str, Any] | str | bool | datetime.date | datetime.time
    ) -> StuffContent:
        # bool must be handled ahead of any future int handling (bool is a subclass of int) and before model_validate,
        # which rejects a bare bool. Covers native YesNoContent and the subclasses generated for concepts refining YesNo.
        if isinstance(value, bool) and issubclass(stuff_content_subclass, YesNoContent):
            return stuff_content_subclass(yes_no=value)
        if isinstance(value, str) and stuff_content_subclass == TextContent:
            return TextContent(text=value)
        # A date/datetime object or an ISO string under a Date-family class builds via the split constructor;
        # a dict ({"date","time"}) still rides model_validate below. Covers native Date and concepts refining it.
        if issubclass(stuff_content_subclass, DateContent) and isinstance(value, (datetime.date, str)):
            return cls._make_date_content(stuff_content_subclass, value=value)
        # A time object or an ISO time string under a Time-family class builds via the split constructor;
        # a dict ({"time": ...}) still rides model_validate below. Covers native Time and concepts refining it.
        if issubclass(stuff_content_subclass, TimeContent) and isinstance(value, (datetime.time, str)):
            return cls._make_time_content(stuff_content_subclass, value=value)
        return stuff_content_subclass.model_validate(obj=value)

    @classmethod
    def _make_date_content(cls, date_subclass: type[DateContent], *, value: datetime.date | str) -> DateContent:
        """Build a DateContent (or refining subclass) from a date/datetime object or a strict ISO string."""
        if isinstance(value, datetime.datetime):
            return date_subclass(date=value.date(), time=value.timetz())
        if isinstance(value, datetime.date):
            return date_subclass(date=value)
        the_date, the_time = cls._parse_iso_temporal(value)
        return date_subclass(date=the_date, time=the_time)

    @classmethod
    def _parse_iso_temporal(cls, value: str) -> tuple[datetime.date, datetime.time | None]:
        """Parse a strict *extended* ISO 8601 date or datetime, date-first so a bare date never fabricates a midnight time."""
        # Require the date component to be extended-calendar YYYY-MM-DD (optionally followed by a T/space time
        # part, which fromisoformat then validates precisely). date.fromisoformat / datetime.fromisoformat (3.11+)
        # also accept the basic "YYYYMMDD" / "YYYYMMDDTHHMMSS" forms and ISO week-dates ("2026-W27-2"), which would
        # silently normalize a non-extended input into a DateContent — and let an all-digit epoch string slip past
        # DateContent's own no-epoch-seconds guard. Pin extended-only (also subsumes the old all-digit reject).
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}([Tt ].*)?", value.strip()):
            msg = f"Date input '{value}' is not an extended ISO 8601 date or datetime (e.g. '2026-07-07' or '2026-07-07T15:40:00+02:00')."
            raise StuffContentFactoryError(msg)
        try:
            return datetime.date.fromisoformat(value), None
        except ValueError:
            pass
        try:
            parsed = datetime.datetime.fromisoformat(value)
        except ValueError as exc:
            msg = f"Date input '{value}' is not an ISO 8601 date or datetime (e.g. '2026-07-07' or '2026-07-07T15:40:00+02:00')."
            raise StuffContentFactoryError(msg) from exc
        return parsed.date(), parsed.timetz()

    @classmethod
    def _make_time_content(cls, time_subclass: type[TimeContent], *, value: datetime.time | str) -> TimeContent:
        """Build a TimeContent (or refining subclass) from a time object or a strict ISO time string."""
        if isinstance(value, datetime.time):
            return time_subclass(time=value)
        # Require the extended HH:MM[:SS] form (optionally with fractional seconds and a UTC offset).
        # time.fromisoformat (3.11+) also accepts the basic "HHMMSS" form, which would let an all-digit
        # string slip past TimeContent's own no-number guard — pin extended-only, mirroring Date.
        if not re.fullmatch(r"\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}(:?\d{2})?)?", value.strip()):
            msg = f"Time input '{value}' is not an extended ISO 8601 time of day (e.g. '15:40:00' or '15:40:00+02:00')."
            raise StuffContentFactoryError(msg)
        try:
            parsed = datetime.time.fromisoformat(value.strip())
        except ValueError as exc:
            msg = f"Time input '{value}' is not an ISO 8601 time of day (e.g. '15:40:00' or '15:40:00+02:00')."
            raise StuffContentFactoryError(msg) from exc
        return time_subclass(time=parsed)

    @classmethod
    def make_stuff_content_from_concept_required(
        cls, concept: Concept, *, value: dict[str, Any] | str | bool | datetime.date | datetime.time
    ) -> StuffContent:
        """Create StuffContent from concept code, requiring the concept to be linked to a class in the registry.
        Raises StuffContentFactoryError if no registry class is found.
        """
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_required_subclass(name=the_subclass_name, base_class=StuffContent)
        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)

    @classmethod
    def make_stuff_content_from_concept_with_fallback(cls, concept: Concept, *, value: dict[str, Any] | str) -> StuffContent:
        """Create StuffContent from concept code, falling back to TextContent if no registry class is found."""
        the_structure_class = get_class_registry().get_class(name=concept.structure_class_name)

        if the_structure_class is None:
            return cls.make_content_from_value(stuff_content_subclass=TextContent, value=value)

        if not issubclass(the_structure_class, StuffContent):
            msg = f"Concept '{concept.code}', subclass '{the_structure_class}' is not a subclass of StuffContent"
            raise StuffContentFactoryError(msg)

        return cls.make_content_from_value(stuff_content_subclass=the_structure_class, value=value)
