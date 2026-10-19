import pytest

from pipelex.tools.misc.string_utils import close_matches


class TestCloseMatches:
    @pytest.mark.parametrize(
        ("cutoff", "max_matches", "expected"),
        [
            pytest.param(0.6, 5, ["summarize_text", "summarize_texts"], id="a_lenient_cutoff_offers_both_near_names"),
            pytest.param(0.99, 5, [], id="a_strict_cutoff_offers_none"),
            pytest.param(0.6, 1, ["summarize_text"], id="the_count_keeps_the_nearest"),
        ],
    )
    def test_the_cutoff_and_the_count_decide_what_is_offered(self, cutoff: float, max_matches: int, expected: list[str]) -> None:
        offered = close_matches(
            name="sumarize_text", candidates=("summarize_text", "summarize_texts", "translate"), cutoff=cutoff, max_matches=max_matches
        )

        assert offered == expected
