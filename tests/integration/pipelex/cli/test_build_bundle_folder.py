"""Pin: ``pipelex build inputs`` and ``pipelex build output`` load a method's whole folder, as ``run bundle`` loads it.

A folder's entry bundle may take a concept from a sibling bundle of its method. The build commands used to validate the
entry bundle alone, so that concept did not resolve and the command failed on a method ``run bundle`` runs. These
drive the real build cores on such a folder, through the resolution the commands make.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.commands.build.inputs._inputs_core import _generate_inputs_core  # pyright: ignore[reportPrivateUsage]
from pipelex.cli.commands.build.output._output_core import _generate_output_core  # pyright: ignore[reportPrivateUsage]
from pipelex.cli.commands.bundle_path_resolver import resolve_build_bundle_target
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat

if TYPE_CHECKING:
    from pathlib import Path

_CONCEPTS_MTHDS = """domain = "pantry_concepts"
description = "What a pantry holds"

[concept.ShoppingList]
description = "The groceries to buy this week"

[concept.Recipe]
description = "A recipe to cook from the pantry"
"""

_ENTRY_MTHDS = """domain = "pantry_cooking"
description = "Cook from what the pantry holds"
main_pipe = "plan_recipe"

[pipe.plan_recipe]
type = "PipeLLM"
description = "Plan a recipe from a shopping list"
inputs = { shopping_list = "pantry_concepts.ShoppingList" }
output = "pantry_concepts.Recipe"
prompt = "Plan a recipe from this shopping list: $shopping_list"
"""

_HINT = "  To use a bundle, pass a .mthds file or directory"


def _write_method_folder(*, directory: Path) -> Path:
    directory.mkdir(parents=True)
    (directory / "concepts.mthds").write_text(_CONCEPTS_MTHDS, encoding="utf-8")
    (directory / "cooking.mthds").write_text(_ENTRY_MTHDS, encoding="utf-8")
    return directory


@pytest.mark.asyncio(loop_scope="class")
class TestBuildBundleFolder:
    async def test_build_inputs_resolves_a_concept_the_entry_takes_from_a_sibling_bundle(self, tmp_path: Path) -> None:
        method_dir = _write_method_folder(directory=tmp_path / "pantry")
        target = resolve_build_bundle_target(
            path=str(method_dir), library_dir=None, pipe_override=None, command="build inputs", not_a_bundle_hint=_HINT
        )

        await _generate_inputs_core(
            pipe_code=target.pipe_code,
            bundle_path=target.bundle_path,
            default_output_dir=target.default_output_dir,
            library_dir=target.library_dir,
        )

        inputs = json.loads((method_dir / "inputs.json").read_text(encoding="utf-8"))
        assert list(inputs) == ["shopping_list"]

    async def test_build_output_resolves_a_concept_the_entry_takes_from_a_sibling_bundle(self, tmp_path: Path) -> None:
        method_dir = _write_method_folder(directory=tmp_path / "pantry")
        target = resolve_build_bundle_target(
            path=str(method_dir), library_dir=None, pipe_override=None, command="build output", not_a_bundle_hint=_HINT
        )
        output_path = tmp_path / "output.json"

        await _generate_output_core(
            pipe_code=target.pipe_code,
            bundle_path=target.bundle_path,
            output_path=output_path,
            default_output_dir=target.default_output_dir,
            output_format=ConceptRepresentationFormat.JSON,
            library_dir=target.library_dir,
        )

        assert output_path.is_file()
