"""Structured content on a log call.

A ``dict``, a ``list`` or a model given as the content is rendered as JSON for the console and carried
as the record's ``data`` attribute for a structured sink: a JSON-ready snapshot of the call, never the
caller's live object.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel

from pipelex import log
from pipelex.tools.log.log_fields import DATA_FIELD

if TYPE_CHECKING:
    import pytest


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The records this test module emitted, whatever else the session's handlers saw."""
    return [record for record in caplog.records if record.name == __name__]


class TestStructuredContent:
    def test_dict_content_is_carried_as_data_and_rendered_for_the_console(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info({"key": "value", "nested": {"flag": True}}, title="Config")

        (record,) = _own_records(caplog)
        assert getattr(record, DATA_FIELD) == {"key": "value", "nested": {"flag": True}}
        rendered = record.getMessage()
        assert rendered.startswith("Config:")
        assert '"key": "value"' in rendered

    def test_list_content_is_carried_as_data(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info([1, "two", {"three": 3}])

        (record,) = _own_records(caplog)
        assert getattr(record, DATA_FIELD) == [1, "two", {"three": 3}]

    def test_data_is_a_snapshot_of_the_call_not_the_callers_live_object(self, caplog: pytest.LogCaptureFixture) -> None:
        """A sink that serializes later, on a queue or a batching exporter, reads what the call said, not what the caller did since."""
        counters: dict[str, Any] = {"seen": 1, "inner": {"flag": False}}
        items: list[Any] = [{"n": 1}]
        with caplog.at_level(logging.INFO):
            log.info(counters)
            log.info(items)
        counters["seen"] = 999
        counters["inner"]["flag"] = True
        items[0]["n"] = 999

        dict_record, list_record = _own_records(caplog)
        assert getattr(dict_record, DATA_FIELD) is not counters
        assert getattr(dict_record, DATA_FIELD) == {"seen": 1, "inner": {"flag": False}}
        assert getattr(list_record, DATA_FIELD) is not items
        assert getattr(list_record, DATA_FIELD) == [{"n": 1}]
        assert json.loads(dict_record.getMessage()) == getattr(dict_record, DATA_FIELD)

    def test_a_list_of_models_is_carried_as_json_ready_data(self, caplog: pytest.LogCaptureFixture) -> None:
        """A python-mode model dump keeps datetimes and the like as objects; ``data`` is what the console rendered, re-read as JSON."""

        class Event(BaseModel):
            when: datetime
            price: Decimal
            ref: UUID

        event = Event(when=datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC), price=Decimal("1.50"), ref=UUID(int=7))
        with caplog.at_level(logging.INFO):
            log.info([event])

        (record,) = _own_records(caplog)
        data = getattr(record, DATA_FIELD)
        assert json.loads(json.dumps(data)) == data
        assert data == json.loads(record.getMessage())
        assert data[0]["when"] == "2020-01-02 03:04:05+00:00"
        assert data[0]["price"] == "1.50"
        assert data[0]["ref"] == str(UUID(int=7))

    def test_string_content_carries_no_data(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info("plain")

        (record,) = _own_records(caplog)
        assert not hasattr(record, DATA_FIELD)

    def test_structured_content_wins_over_a_data_field(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info({"from": "content"}, fields={DATA_FIELD: "from-field"})

        (record,) = _own_records(caplog)
        assert getattr(record, DATA_FIELD) == {"from": "content"}

    def test_none_content_is_rendered_as_the_word_none_without_data(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info(None, title="Empty")

        (record,) = _own_records(caplog)
        assert record.getMessage() == "Empty:\nNone"
        assert not hasattr(record, DATA_FIELD)

    def test_a_circular_reference_is_rendered_as_its_repr_and_never_raises(self, caplog: pytest.LogCaptureFixture) -> None:
        """``json.dumps`` raises ``ValueError`` on a cycle, which the JSON helpers do not catch; a log call never raises."""
        cyclic: dict[str, Any] = {"name": "loop"}
        cyclic["self"] = cyclic
        with caplog.at_level(logging.INFO):
            log.info(cyclic, title="Cycle")

        (record,) = _own_records(caplog)
        assert record.getMessage().startswith("Cycle:\n")
        assert "loop" in record.getMessage()
        assert not hasattr(record, DATA_FIELD)

    def test_a_non_string_key_is_rendered_as_its_repr_and_never_raises(self, caplog: pytest.LogCaptureFixture) -> None:
        """``json.dumps`` applies ``default`` to values and not to keys, so a tuple key raises ``TypeError`` from every fallback."""
        keyed: dict[Any, Any] = {(1, 2): "a"}
        with caplog.at_level(logging.INFO):
            log.info(keyed)

        (record,) = _own_records(caplog)
        assert "(1, 2)" in record.getMessage()
        assert not hasattr(record, DATA_FIELD)

    def test_a_scalar_content_is_carried_as_itself(self, caplog: pytest.LogCaptureFixture) -> None:
        """``data`` is whatever the JSON rendering parses back to, a scalar for a scalar content."""
        with caplog.at_level(logging.INFO):
            log.info(42)

        (record,) = _own_records(caplog)
        assert getattr(record, DATA_FIELD) == 42
