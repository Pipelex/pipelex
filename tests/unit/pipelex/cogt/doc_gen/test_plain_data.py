import datetime
from enum import StrEnum

from pipelex.cogt.doc_gen.plain_data import plain_data
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_content import TextContent


class _Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class _Tagged(StructuredContent):
    name: str
    colors: set[_Color]
    codes: frozenset[str]


class TestPlainData:
    def test_a_structure_is_a_dict_of_its_fields(self) -> None:
        tagged = _Tagged(name="Ada", colors={_Color.RED, _Color.BLUE}, codes=frozenset({"b", "a"}))
        assert plain_data(tagged) == {"name": "Ada", "colors": ["blue", "red"], "codes": ["a", "b"]}

    def test_a_composite_is_a_dict_of_its_components(self) -> None:
        composite = CompositeContent.model_validate({"summary": TextContent(text="All good."), "score": NumberContent(number=3)})
        assert plain_data(composite) == {"summary": "All good.", "score": 3}

    def test_a_list_stuff_is_a_list(self) -> None:
        texts = ListContent[TextContent](items=[TextContent(text="one"), TextContent(text="two")])
        assert plain_data(texts) == ["one", "two"]

    def test_a_date_with_a_time_of_day_is_a_datetime(self) -> None:
        assert plain_data(DateContent(date=datetime.date(2026, 9, 30))) == datetime.date(2026, 9, 30)
        with_time = DateContent(date=datetime.date(2026, 9, 30), time=datetime.time(9, 30))
        assert plain_data(with_time) == datetime.datetime(2026, 9, 30, 9, 30)
