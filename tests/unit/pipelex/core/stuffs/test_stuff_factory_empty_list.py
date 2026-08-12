"""The empty list at the bottom-up factory: a value when the concept is known, an error when it is not.

A plural slot is never *absent* in MTHDS — when nothing is found, it is the empty list. The
top-down shaper has always honoured that for a bare `[]` (D2). This module pins the same verdict
for the `{concept, content}` envelope, and pins the one case that must still fail: a bare empty
list with no concept anywhere, whose item type is genuinely unknowable.
"""

from pathlib import Path
from typing import Callable, cast

import pytest

from pipelex import pretty_print
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.interpreter_hub import get_concept_library


@pytest.fixture(scope="class")
def empty_list_library(load_test_library: Callable[[list[Path]], None]):
    load_test_library([Path(__file__).parent])


@pytest.mark.usefixtures("empty_list_library")
class TestStuffFactoryEmptyList:
    @pytest.mark.parametrize("concept_ref", ["native.Image", "native.Text", "native.Document"])
    def test_envelope_empty_list_builds_empty_list_content(self, concept_ref: str) -> None:
        """Case 2.7: the envelope names the concept, so an empty list needs no item-type inference.

        Regression: this raised "Cannot create Stuff from empty list in content", which made a
        plural input with nothing in it unrunnable through the envelope spelling.
        """
        result = StuffFactory.make_stuff_from_stuff_content_or_data(
            stuff_content_or_data={"concept": concept_ref, "content": []},
            concept_provider=get_concept_library(),
            name="pics",
        )

        pretty_print(result, title=f"empty list under {concept_ref}")
        assert result.concept.concept_ref == concept_ref
        assert result.content == ListContent(items=[])
        assert result.stuff_name == "pics"

    def test_empty_list_content_is_falsy_and_iterates_zero_times(self) -> None:
        """What makes the empty ListContent safe downstream: a template guard sees it as empty.

        `{% if pics %}` must not render a heading over an empty gallery, and `{% for %}` must
        produce nothing — so a method written for "pictures when there are pictures" behaves.
        """
        result = StuffFactory.make_stuff_from_stuff_content_or_data(
            stuff_content_or_data={"concept": "native.Image", "content": []},
            concept_provider=get_concept_library(),
            name="pics",
        )

        content = cast("ListContent[StuffContent]", result.content)
        assert isinstance(content, ListContent)
        assert not content
        assert len(content) == 0
        assert list(content) == []

    def test_bare_empty_list_without_concept_still_raises(self) -> None:
        """Case 1.5 must keep failing: with no concept there is nothing to infer an item type from.

        This is the boundary of the fix — the envelope carries the answer, a naked list does not.
        """
        with pytest.raises(StuffFactoryError, match="empty"):
            StuffFactory.make_stuff_from_stuff_content_or_data(
                stuff_content_or_data=ListContent[StuffContent](items=[]),
                concept_provider=get_concept_library(),
                name="pics",
            )

    def test_non_empty_envelope_list_is_unaffected(self) -> None:
        """The populated path keeps inferring from the first item exactly as before."""
        result = StuffFactory.make_stuff_from_stuff_content_or_data(
            stuff_content_or_data={"concept": "native.Text", "content": ["a", "b"]},
            concept_provider=get_concept_library(),
            name="notes",
        )

        assert result.concept.concept_ref == "native.Text"
        content = cast("ListContent[StuffContent]", result.content)
        assert isinstance(content, ListContent)
        assert len(content) == 2
