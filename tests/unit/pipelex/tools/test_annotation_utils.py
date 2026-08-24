from typing import Any, Optional, Union

import pytest

from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.typing.annotation_utils import unwrap_optional


class TestUnwrapOptional:
    """unwrap_optional must unwrap the Optional shape (single non-None arm) in both the
    typing.Union and PEP 604 spellings, and leave every other annotation unchanged.
    """

    @pytest.mark.parametrize(
        ("annotation", "expected"),
        [
            pytest.param(Optional[str], str, id="typing_optional_str"),  # ruff: ignore[non-pep604-annotation-optional] — the typing.Optional spelling is the test subject
            pytest.param(Union[str, None], str, id="typing_union_str_none"),
            pytest.param(str | None, str, id="pep604_str_none"),
            pytest.param(Optional[list[str]], list[str], id="typing_optional_list_str"),  # ruff: ignore[non-pep604-annotation-optional] — the typing.Optional spelling is the test subject
            pytest.param(list[str] | None, list[str], id="pep604_list_str_none"),
            pytest.param(Optional[TextContent], TextContent, id="typing_optional_text_content"),  # ruff: ignore[non-pep604-annotation-optional] — the typing.Optional spelling is the test subject
            pytest.param(TextContent | None, TextContent, id="pep604_text_content_none"),
        ],
    )
    def test_unwraps_optional_shape(self, annotation: Any, expected: Any):
        assert unwrap_optional(annotation) == expected

    @pytest.mark.parametrize(
        "annotation",
        [
            pytest.param(str, id="bare_class"),
            pytest.param(list[str], id="generic_list"),
            pytest.param(dict[str, int], id="generic_dict"),
            pytest.param(Union[str, int], id="typing_union_multi_arm"),
            pytest.param(str | int, id="pep604_union_multi_arm"),
            pytest.param(Union[str, int, None], id="typing_union_multi_arm_with_none"),
            pytest.param(str | int | None, id="pep604_union_multi_arm_with_none"),
            pytest.param(None, id="none_annotation"),
        ],
    )
    def test_leaves_non_optional_shapes_unchanged(self, annotation: Any):
        assert unwrap_optional(annotation) == annotation
