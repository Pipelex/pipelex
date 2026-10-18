"""A name declared twice, or colliding with a native concept, is located on the declaration that collides.

Each `method.name_conflict` item names the table that declares the colliding name by its bundle-root path, such as
`concept.Rating`, and the bundle file it is declared in whenever the caller named that file, in a validation verdict
and in a run's refusal alike.
"""

from operator import itemgetter
from typing import Any, ClassVar

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle


class _NameConflictData:
    NATIVE_REDECLARATION: ClassVar[str] = """
domain = "name_conflict_native"
main_pipe = "echo"

[concept.Rating]
description = "A rating, declared again"

[pipe.echo]
type = "PipeCompose"
description = "Echo"
inputs = { text = "Text" }
output = "Text"
template = "{{ text }}"
"""
    FIRST: ClassVar[str] = """
domain = "name_conflict_dup"
main_pipe = "echo"

[concept]
Doc = "A document, as the first bundle declares it"

[pipe.echo]
type = "PipeCompose"
description = "Echo"
inputs = { text = "Text" }
output = "Text"
template = "{{ text }}"
"""
    SECOND: ClassVar[str] = """
domain = "name_conflict_dup"

[concept]
Doc = "A document, as the second bundle declares it"
"""
    # A second bundle declaring the first one's pipe again.
    SECOND_PIPE: ClassVar[str] = """
domain = "name_conflict_dup"

[pipe.echo]
type = "PipeCompose"
description = "Echo, as the second bundle declares it"
inputs = { text = "Text" }
output = "Text"
template = "{{ text }}"
"""


def _name_conflict_locations(error: PipelexError) -> list[dict[str, Any]]:
    """The locations of the caller's `method.name_conflict` items, or of the problem itself when it is the one fault."""
    problem = error.to_problem(view=ProblemView.CALLER)
    if problem.code == CoreCode.METHOD_NAME_CONFLICT:
        assert problem.location is not None
        return [problem.location.as_wire()]
    assert problem.errors is not None, problem
    locations: list[dict[str, Any]] = []
    for item in problem.errors:
        if item.code == CoreCode.METHOD_NAME_CONFLICT:
            assert item.location is not None, item
            locations.append(item.location.as_wire())
    return locations


@pytest.mark.asyncio(loop_scope="class")
class TestNameConflictLocation:
    @pytest.mark.parametrize(
        ("sources", "expected_locations"),
        [
            pytest.param(["bundle.mthds"], [{"field": "concept.Rating", "file": "bundle.mthds"}], id="named_file"),
            pytest.param(None, [{"field": "concept.Rating"}], id="unnamed_content"),
        ],
    )
    async def test_a_conflict_inside_one_bundle_is_located_on_its_declaration(
        self, sources: list[str | None] | None, expected_locations: list[dict[str, Any]]
    ) -> None:
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_NameConflictData.NATIVE_REDECLARATION], mthds_sources=sources)

        assert _name_conflict_locations(exc_info.value) == expected_locations

    async def test_a_conflict_across_two_bundles_is_located_on_each_declaration(self) -> None:
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[_NameConflictData.FIRST, _NameConflictData.SECOND], mthds_sources=["first.mthds", "second.mthds"])

        assert sorted(_name_conflict_locations(exc_info.value), key=itemgetter("file")) == [
            {"field": "concept.Doc", "file": "first.mthds"},
            {"field": "concept.Doc", "file": "second.mthds"},
        ]

    async def test_a_pipe_declared_twice_is_located_by_its_path_from_the_bundle_root_alone(self) -> None:
        """A pipe's declaration is located by its bundle-root path, with no `pipe` beside it that a reader would join to it."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(
                mthds_contents=[_NameConflictData.FIRST, _NameConflictData.SECOND_PIPE], mthds_sources=["first.mthds", "second.mthds"]
            )

        assert sorted(_name_conflict_locations(exc_info.value), key=itemgetter("file")) == [
            {"field": "pipe.echo", "file": "first.mthds"},
            {"field": "pipe.echo", "file": "second.mthds"},
        ]

    @pytest.mark.parametrize(
        ("contents", "expected_locations"),
        [
            pytest.param([_NameConflictData.NATIVE_REDECLARATION], [{"field": "concept.Rating"}], id="one_bundle"),
            pytest.param(
                [_NameConflictData.FIRST, _NameConflictData.SECOND],
                [{"field": "concept.Doc"}, {"field": "concept.Doc"}],
                id="two_bundles",
            ),
        ],
    )
    async def test_a_run_s_refusal_locates_the_conflict_on_its_declaration(
        self, contents: list[str], expected_locations: list[dict[str, Any]]
    ) -> None:
        """A run of content refuses the method before any pipe runs, its items located as the verdict's are."""
        with pytest.raises(PipelexError) as exc_info:
            await PipelexMTHDSProtocol().execute(mthds_contents=contents, inputs={"text": "x"})

        assert _name_conflict_locations(exc_info.value) == expected_locations
