from typing import Any

from pytest_mock import MockerFixture

from pipelex_api import request_refusals
from pipelex_api.request_refusals import MAX_REFUSED_FIELDS, refused_request_error

# How many faults past the bound a refusal reports, as a list the caller sent can fail item by item.
_EXTRA_FAULT_COUNT = 7


def _item_faults(*, count: int) -> list[dict[str, Any]]:
    """One fault per item of a list field, as FastAPI reports them, each located in the body."""
    return [{"loc": ("body", "callback_urls", index_fault), "msg": "Value error, malformed", "type": "value_error"} for index_fault in range(count)]


class TestRequestRefusals:
    def test_the_message_names_as_many_faults_as_the_items_then_how_many_more(self):
        # The items stop at `MAX_REFUSED_FIELDS`, and so does the operator's account, which says how many it left out
        # rather than growing with whatever the caller sent.
        faults = _item_faults(count=MAX_REFUSED_FIELDS + _EXTRA_FAULT_COUNT)
        refusal = refused_request_error(faults=faults, located_by_request_part=True)
        described = refusal.message.split("; ")
        assert len(described) == MAX_REFUSED_FIELDS + 1
        assert described[0] == "callback_urls.0: Value error, malformed"
        assert described[MAX_REFUSED_FIELDS - 1] == f"callback_urls.{MAX_REFUSED_FIELDS - 1}: Value error, malformed"
        assert described[-1] == f"and {_EXTRA_FAULT_COUNT} more"
        items = refusal.problem_items()
        assert items is not None
        assert len(items) == MAX_REFUSED_FIELDS

    def test_a_message_within_the_bound_names_every_fault(self):
        refusal = refused_request_error(faults=_item_faults(count=2), located_by_request_part=True)
        assert refusal.message == "callback_urls.0: Value error, malformed; callback_urls.1: Value error, malformed"

    def test_each_fault_s_path_is_read_once(self, mocker: MockerFixture):
        faults = _item_faults(count=3)
        path_spy = mocker.spy(request_refusals, "_fault_field_path")
        refused_request_error(faults=faults, located_by_request_part=True)
        assert path_spy.call_count == len(faults)
