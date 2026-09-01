"""Pin the D6 `build_pipe_io_contracts` builder: typed `PipeIOContract` entries keyed by `pipe_ref`.

Covers the two combinations the hosted builder it was ported from never saw:

- **`PipeSignature` pipes in a lenient batch** — a forward-declared header validated with
  ``allow_signatures=True`` gets an IO-contract entry like any concrete pipe (its declared
  contract is exactly what a top-down build needs), keyed by its namespaced ``pipe_ref``.
- **Multiplicity entry shapes** — a single output reports ``multiplicity="single"``, a
  variable list output (``Concept[]``) reports ``multiplicity="variable"``, and a fixed-count
  output (``Concept[N]``) reports ``multiplicity="fixed"`` with ``item_count=N``; list-typed
  inputs carry the same projection plus an array JSON Schema.

The builder runs against the open validation library (`validate_bundle` leaves it loaded on
success), mirroring how the protocol wrapper consumes it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import PydanticUserError

from pipelex.core.pipes.variable_multiplicity import PresenceMarker
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.exceptions import PipeIOContractError
from pipelex.pipeline.pipe_io_contracts import IOMultiplicity, build_pipe_io_contracts
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

[pipe.make_two]
type = "PipeLLM"
description = "Make exactly two items"
inputs = { docs = "Text[2]" }
output = "Item[2]"
prompt = "Make two items from:\\n@docs"

[pipe.make_from_one]
type = "PipeLLM"
description = "Make an item from a [1]-declared doc"
inputs = { docs = "Text[1]" }
output = "Item"
prompt = "Make an item from:\\n@docs"
"""


_OPTIONAL_MTHDS = """
domain = "optional_contracts_test"
description = "Bundle exercising presence markers on IO contracts"

[concept.Verdict]
description = "A verdict"

[pipe.assess]
type = "PipeLLM"
description = "Assess with an optional hint"
inputs = { doc = "Text", hint = "Text?", brief = "Text!" }
output = "Verdict"
prompt = '''
Assess $doc following $brief.
@?hint
'''

[pipe.check]
type = "PipeLLM"
description = "Check the doc"
inputs = { doc = "Text" }
output = "Verdict"
prompt = "Check $doc"

[pipe.gate]
type = "PipeCondition"
description = "Gate that may continue with no output"
inputs = { doc = "Text" }
output = "Verdict?"
expression = "doc"
default_outcome = "continue"

[pipe.gate.outcomes]
go = "check"
"""


_ANYTHING_MTHDS = """
domain = "anything_contracts_test"
description = "Bundle exercising the structureless native.Anything at input positions"

[pipe.carry]
type = "PipeCompose"
description = "Carry an untyped payload through"
inputs = { anything_in = "Anything", batch_in = "Anything[]", pair_in = "Anything[2]" }
output = "Text"
template = "$anything_in $batch_in $pair_in"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestBuildPipeIOContracts:
    async def test_optional_markers_reported_on_contracts(self, load_empty_library: Callable[[], str]) -> None:
        """A `?`-declared input reports presence=optional; plain ones plain; a `?` output optional=True."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_OPTIONAL_MTHDS])
            io_contracts = build_pipe_io_contracts(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        assess = io_contracts["optional_contracts_test.assess"]
        assert assess.inputs["doc"].presence == PresenceMarker.PLAIN
        assert assess.inputs["hint"].presence == PresenceMarker.OPTIONAL
        assert assess.inputs["brief"].presence == PresenceMarker.FORCE
        assert assess.output.optional is False

        gate = io_contracts["optional_contracts_test.gate"]
        assert gate.output.optional is True

    async def test_multiplicity_entry_shapes(self, load_empty_library: Callable[[], str]) -> None:
        """Entries are keyed by namespaced pipe_ref; output multiplicity is single vs variable."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_MULTIPLICITY_MTHDS])
            io_contracts = build_pipe_io_contracts(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        assert set(io_contracts) == {
            "structures_test.make_one",
            "structures_test.make_many",
            "structures_test.make_two",
            "structures_test.make_from_one",
        }

        make_one = io_contracts["structures_test.make_one"]
        assert make_one.output.concept_ref == "structures_test.Item"
        assert make_one.output.multiplicity == IOMultiplicity.SINGLE
        assert make_one.output.item_count is None
        assert make_one.inputs["doc"].concept_ref == "native.Text"
        assert make_one.inputs["doc"].multiplicity == IOMultiplicity.SINGLE
        assert make_one.inputs["doc"].item_count is None
        assert make_one.inputs["doc"].json_schema

        make_many = io_contracts["structures_test.make_many"]
        assert make_many.output.concept_ref == "structures_test.Item"
        assert make_many.output.multiplicity == IOMultiplicity.VARIABLE
        assert make_many.output.item_count is None
        assert make_many.inputs["docs"].multiplicity == IOMultiplicity.VARIABLE
        assert make_many.inputs["docs"].item_count is None
        # A list-typed input renders an array JSON Schema, unbounded on the variable arm.
        docs_schema = make_many.inputs["docs"].json_schema
        assert docs_schema.get("type") == "array"
        assert "minItems" not in docs_schema
        assert "maxItems" not in docs_schema

        make_two = io_contracts["structures_test.make_two"]
        assert make_two.output.multiplicity == IOMultiplicity.FIXED
        assert make_two.output.item_count == 2
        assert make_two.inputs["docs"].multiplicity == IOMultiplicity.FIXED
        assert make_two.inputs["docs"].item_count == 2
        # The fixed-count input renders a bounded array JSON Schema.
        two_schema = make_two.inputs["docs"].json_schema
        assert two_schema.get("type") == "array"
        assert two_schema.get("minItems") == 2
        assert two_schema.get("maxItems") == 2

        # A `[1]` input projects to single: no count, no array framing — and the schema memo
        # must not serve it another arm's schema (the memo key normalizes multiplicity because
        # `hash(True) == hash(1)` would collide `Text[]` with `Text[1]` under a raw key).
        make_from_one = io_contracts["structures_test.make_from_one"]
        assert make_from_one.inputs["docs"].multiplicity == IOMultiplicity.SINGLE
        assert make_from_one.inputs["docs"].item_count is None
        one_schema = make_from_one.inputs["docs"].json_schema
        assert one_schema.get("type") != "array"

    async def test_anything_input_publishes_permissive_schema(self, load_empty_library: Callable[[], str]) -> None:
        """A `native.Anything` input renders instead of crashing: the contract publishes the
        permissive schema — no constraint keywords, only the concept's identity annotations —
        with multiplicity wrapping exactly as for class-backed concepts.
        """
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_ANYTHING_MTHDS])
            io_contracts = build_pipe_io_contracts(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        carry = io_contracts["anything_contracts_test.carry"]

        single = carry.inputs["anything_in"]
        assert single.concept_ref == "native.Anything"
        assert single.multiplicity == IOMultiplicity.SINGLE
        assert single.json_schema["title"] == "native.Anything"
        assert single.json_schema["description"]
        assert set(single.json_schema) == {"title", "description"}

        batch = carry.inputs["batch_in"]
        assert batch.multiplicity == IOMultiplicity.VARIABLE
        assert batch.json_schema["type"] == "array"
        assert batch.json_schema["items"]["title"] == "native.Anything"
        assert "minItems" not in batch.json_schema

        pair = carry.inputs["pair_in"]
        assert pair.multiplicity == IOMultiplicity.FIXED
        assert pair.item_count == 2
        assert pair.json_schema["minItems"] == 2
        assert pair.json_schema["maxItems"] == 2

    async def test_schema_render_failure_converts_to_structured_error(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
    ) -> None:
        """A pydantic schema-generation failure converts to PipeIOContractError with pipe/input
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
            with pytest.raises(PipeIOContractError, match="Failed to render the JSON Schema"):
                build_pipe_io_contracts(result.pipes)
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
            io_contracts = build_pipe_io_contracts(result.pipes)
        finally:
            _teardown_validation_library(outer_library_id)

        # The signature (forward declaration) and the controller referencing it both report contracts.
        signature_contract = io_contracts["research.find_key_findings"]
        assert signature_contract.output.concept_ref == "research.KeyFinding"
        assert signature_contract.output.multiplicity == IOMultiplicity.SINGLE
        assert signature_contract.inputs["doc"].concept_ref == "native.Text"

        controller_contract = io_contracts["research.research_brief"]
        assert controller_contract.output.concept_ref == "research.KeyFinding"
