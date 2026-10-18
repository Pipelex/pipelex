"""A declaration made twice is one fault per bundle that makes it, and one bundle's only when both sources name it."""

import pytest

from pipelex.libraries.collision_messages import DeclarationKind, duplicate_ref_items


class TestDuplicateRefItems:
    @pytest.mark.parametrize(
        ("existing_source", "incoming_source", "expected_items"),
        [
            pytest.param(
                "first.mthds",
                "second.mthds",
                [
                    ("second.mthds", "Pipe 'scoring.compute_score' is declared here and in 'first.mthds'."),
                    ("first.mthds", "Pipe 'scoring.compute_score' is declared here and in 'second.mthds'."),
                ],
                id="two_bundles",
            ),
            pytest.param(
                "first.mthds",
                "first.mthds",
                [("first.mthds", "Pipe 'scoring.compute_score' is declared twice in this bundle.")],
                id="one_bundle",
            ),
            pytest.param(
                None,
                "second.mthds",
                [
                    ("second.mthds", "Pipe 'scoring.compute_score' is declared here and in 'unknown'."),
                    (None, "Pipe 'scoring.compute_score' is declared here and in 'second.mthds'."),
                ],
                id="one_source_unknown",
            ),
            pytest.param(
                None,
                None,
                [
                    (None, "Pipe 'scoring.compute_score' is declared here and in 'unknown'."),
                    (None, "Pipe 'scoring.compute_score' is declared here and in 'unknown'."),
                ],
                id="both_sources_unknown_are_not_one_bundle",
            ),
        ],
    )
    def test_each_declaration_is_an_item_on_its_bundle(
        self, existing_source: str | None, incoming_source: str | None, expected_items: list[tuple[str | None, str]]
    ) -> None:
        items = duplicate_ref_items(
            ref_kind=DeclarationKind.PIPE, ref="scoring.compute_score", existing_source=existing_source, incoming_source=incoming_source
        )

        assert [(item.source, item.message) for item in items] == expected_items
        assert all(item.params == {"name": "scoring.compute_score", "conflict": "duplicate_declaration"} for item in items)
