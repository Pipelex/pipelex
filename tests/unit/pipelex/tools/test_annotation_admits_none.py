from typing import Annotated, Any, Literal, Optional, Union

import pytest

from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.typing.annotation_utils import annotation_admits_none


class TestAnnotationAdmitsNone:
    """annotation_admits_none must say whether pydantic accepts `None` for a field so annotated, whatever spelling admits it."""

    @pytest.mark.parametrize(
        "annotation",
        [
            pytest.param(None, id="none_annotation"),
            pytest.param(type(None), id="none_type"),
            pytest.param(Any, id="any"),
            pytest.param(object, id="object"),
            pytest.param(Optional[str], id="typing_optional_str"),  # ruff: ignore[non-pep604-annotation-optional] — the typing.Optional spelling is the test subject
            pytest.param(Union[str, None], id="typing_union_str_none"),
            pytest.param(str | None, id="pep604_str_none"),
            pytest.param(str | int | None, id="pep604_union_multi_arm_with_none"),
            pytest.param(TextContent | None, id="pep604_text_content_none"),
            pytest.param(Literal["fallback", None], id="literal_listing_none"),  # ruff: ignore[redundant-none-literal] — a Literal listing None is the test subject
            pytest.param(Literal["fallback"] | None, id="pep604_literal_none"),
            pytest.param(str | Any, id="union_with_any"),
            pytest.param(Annotated[str | None, "note"] | int, id="union_with_annotated_optional_arm"),
            pytest.param(Annotated[str | None, "note"], id="annotated_optional"),
        ],
    )
    def test_admits_none(self, annotation: Any):
        assert annotation_admits_none(annotation=annotation)

    @pytest.mark.parametrize(
        "annotation",
        [
            pytest.param(str, id="bare_class"),
            pytest.param(TextContent, id="content_class"),
            pytest.param(list[str | None], id="list_of_optional_items"),
            pytest.param(str | int, id="pep604_union_multi_arm"),
            pytest.param(Literal["fallback", "other"], id="literal_without_none"),
            pytest.param(Annotated[str, "note"] | int, id="union_with_annotated_required_arm"),
        ],
    )
    def test_refuses_none(self, annotation: Any):
        assert not annotation_admits_none(annotation=annotation)
