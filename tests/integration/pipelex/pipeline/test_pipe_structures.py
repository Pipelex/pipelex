"""Pin the D6 `build_pipe_structures` builder: typed `PipeIOContract` entries keyed by `pipe_ref`.

Covers the two combinations the hosted builder it was ported from never saw:

- **`PipeSignature` pipes in a lenient batch** — a forward-declared header validated with
  ``allow_signatures=True`` gets a structures entry like any concrete pipe (its declared
  contract is exactly what a top-down build needs), keyed by its namespaced ``pipe_ref``.
- **Multiplicity entry shapes** — a single output reports ``multiplicity="single"``, a
  list output (``Concept[]``) reports ``multiplicity="variable"`` with an array JSON Schema
  on list-typed inputs.

The builder runs against the open validation library (`validate_bundle` leaves it loaded on
success), mirroring how the protocol wrapper consumes it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import PydanticUserError

from pipelex.hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.exceptions import PipeStructuresError
from pipelex.pipeline.pipe_structures import IOMultiplicity, build_pipe_structures
from pipelex.pipeline.validate_bundle import validate_bundle

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture


def _teardown_validation_library(outer_library_id: str) -> None:
    """Tear down the library `validate_bundle` left open on success, restoring the outer one."""
    validation_library_id = get_current_library_id_or_none()
    if validation_library_id is not None and validation_library_id != outer_library_id:
        set_current_library(library_id=outer_library_id)
        get_library_manager().teardown(library_id=validation_library_id)
    clear_current_library()


_SIGNATURE_ONLY_DIR = Path(__file__).parents[3] / "e2e" / "pipelex" / "pipes" / "additive_multi_file_library" / "signature_only"

_MULTIPLICITY_MTHDS = """
domain = "structures_test"
description = "Bundle exercising single and variable output multiplicities"

[concept.Item]
description = "An item"

[pipe.make_one]
type = "PipeLLM"
description = "Make one item"
inputs = { doc = "Text" }
output = "Item"
prompt = "Make one item from $doc"

[pipe.make_many]
type = "PipeLLM"
description = "Make many items"
inputs = { docs = "Text[]" }
output = "Item[]"
prompt = "Make items from:\\n@docs"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestBuildPipeStructures:
    async def test_multiplicity_entry_shapes(self, load_empty_library: Callable[[], str]) -> None:
        """Entries are keyed by namespaced pipe_ref; output multiplicity is single vs variable."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_MULTIPLICITY_MTHDS])
            structures = build_pipe_structures(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        assert set(structures) == {"structures_test.make_one", "structures_test.make_many"}

        make_one = structures["structures_test.make_one"]
        assert make_one.output.concept_code == "structures_test.Item"
        assert make_one.output.multiplicity == IOMultiplicity.SINGLE
        assert make_one.inputs["doc"].concept_code == "native.Text"
        assert make_one.inputs["doc"].json_schema

        make_many = structures["structures_test.make_many"]
        assert make_many.output.concept_code == "structures_test.Item"
        assert make_many.output.multiplicity == IOMultiplicity.VARIABLE
        # A list-typed input renders an array JSON Schema.
        assert make_many.inputs["docs"].json_schema.get("type") == "array"

    async def test_schema_render_failure_converts_to_structured_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """A pydantic schema-generation failure converts to PipeStructuresError with pipe/input
        context — never a raw third-party error (which the Temporal boundary would not convert
        and Temporal would pointlessly retry).
        """
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_MULTIPLICITY_MTHDS])
            mocker.patch(
                "pipelex.core.pipes.stuff_spec.stuff_spec.StuffSpec.render_stuff_spec",
                side_effect=PydanticUserError("simulated schema-generation failure", code=None),
            )
            with pytest.raises(PipeStructuresError, match="Failed to render the JSON Schema"):
                build_pipe_structures(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

    async def test_signature_pipes_in_lenient_batch(self, load_empty_library: Callable[[], str]) -> None:
        """A PipeSignature header in a lenient batch gets a contract entry like any concrete pipe."""
        outer_library_id = load_empty_library()
        try:
            mthds_contents = [
                (_SIGNATURE_ONLY_DIR / "concepts.mthds").read_text(encoding="utf-8"),
                (_SIGNATURE_ONLY_DIR / "header.mthds").read_text(encoding="utf-8"),
            ]
            result = await validate_bundle(mthds_contents=mthds_contents, allow_signatures=True)
            structures = build_pipe_structures(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        # The signature (forward declaration) and the controller referencing it both report contracts.
        signature_contract = structures["research.find_key_findings"]
        assert signature_contract.output.concept_code == "research.KeyFinding"
        assert signature_contract.output.multiplicity == IOMultiplicity.SINGLE
        assert signature_contract.inputs["doc"].concept_code == "native.Text"

        controller_contract = structures["research.research_brief"]
        assert controller_contract.output.concept_code == "research.KeyFinding"
