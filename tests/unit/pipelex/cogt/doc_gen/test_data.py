import datetime
from typing import ClassVar

from pipelex.cogt.doc_gen.layout_tree import LayoutScalar


class LayoutDisplayTestData:
    """Each scalar case: (value, its text). Each numeric column case: (topic, values, whether the column is numeric)."""

    SCALAR_CASES: ClassVar[list[tuple[LayoutScalar, str]]] = [
        (None, ""),
        (True, "Yes"),
        (False, "No"),
        (42, "42"),
        (2.0, "2"),
        (2.5, "2.5"),
        (0.1 + 0.2, "0.3"),
        (datetime.date(2026, 9, 29), "2026-09-29"),
        (datetime.datetime(2026, 9, 29, 14, 5, 59), "2026-09-29 14:05"),
        (datetime.time(9, 7, 30), "09:07"),
        (datetime.datetime(2026, 9, 29, 14, 5, tzinfo=datetime.UTC), "2026-09-29 14:05 UTC"),
        (datetime.datetime(2026, 9, 29, 14, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=2))), "2026-09-29 14:05 +02:00"),
        (datetime.time(9, 7, tzinfo=datetime.timezone(datetime.timedelta(hours=-5, minutes=-30))), "09:07 -05:30"),
        ("As written", "As written"),
    ]

    NUMERIC_COLUMN_CASES: ClassVar[list[tuple[str, list[LayoutScalar], bool]]] = [
        ("integers and floats", [1, 2.5, 3], True),
        ("numbers with blanks", [None, 4, None], True),
        ("no rows", [], False),
        ("blanks only", [None, None], False),
        ("booleans", [True, False], False),
        ("a boolean among numbers", [1, True], False),
        ("a text among numbers", [1, "2"], False),
        ("dates", [datetime.date(2026, 9, 29)], False),
    ]
