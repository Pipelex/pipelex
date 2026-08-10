import datetime
import re
from typing import Any

from pipelex.core.concepts.concept import Concept
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.exceptions import StuffContentFactoryError
from pipelex.core.stuffs.iso_temporal import parse_iso_date, parse_iso_time
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
        """Parse a strict *extended* ISO 8601 date or datetime, keeping a bare date's absent time absent."""
        # Split on the date/time separator and hand each half to the parser the content models use, so an
        # authored "2026-07-07T15:40:00" and a model-generated {date, time} pair are held to one contract —
        # down to the basic spellings and the end-of-day 24:00 form. Splitting rather than calling
        # datetime.fromisoformat is what makes the time half reachable by that parser at all.
        match = re.fullmatch(r"(?P<date>\d{4}-\d{2}-\d{2})(?:[Tt ](?P<time>.+))?", value)
        if not match:
            msg = f"Date input '{value}' is not an extended ISO 8601 date or datetime (e.g. '2026-07-07' or '2026-07-07T15:40:00+02:00')."
            raise StuffContentFactoryError(msg)
        time_text = match.group("time")
        try:
            the_date = parse_iso_date(match.group("date"))
            the_time = parse_iso_time(time_text) if time_text is not None else None
        except ValueError as exc:
            msg = f"Date input '{value}' is not an extended ISO 8601 date or datetime (e.g. '2026-07-07' or '2026-07-07T15:40:00+02:00'): {exc}"
            raise StuffContentFactoryError(msg) from exc
        return the_date, the_time

    @classmethod
    def _make_time_content(cls, time_subclass: type[TimeContent], *, value: datetime.time | str) -> TimeContent:
        """Build a TimeContent (or refining subclass) from a time object or a strict ISO time string."""
        if isinstance(value, datetime.time):
            return time_subclass(time=value)
        # Delegate to the parser the content models use, so an authored time and a model-generated one
        # are held to the same extended-ISO contract (and both reject the end-of-day 24:00 form, which
        # Python 3.14 would otherwise read as this day's midnight rather than the next day's).
        try:
            parsed = parse_iso_time(value)
        except ValueError as exc:
            msg = f"Time input '{value}' is not an extended ISO 8601 time of day (e.g. '15:40:00' or '15:40:00+02:00')."
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
