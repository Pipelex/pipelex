from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager
from pipelex.pipeline.inputs_template import build_inputs_for_pipe

if TYPE_CHECKING:
    from pathlib import Path

_MANIFEST = """\
[package]
address = "github.com/pipelex-tests/summaries"
version = "1.0.0"
description = "A method offering example inputs"
main_pipe = "summarize"
examples = ["examples/demo.json"]

[exports.alpha]
pipes = ["summarize"]
"""


def _bundle(domain: str) -> str:
    return f"""\
domain = "{domain}"
description = "The {domain} summaries"
main_pipe = "summarize"

[pipe.summarize]
type = "PipeCompose"
description = "Summarize a text"
inputs = {{ text = "Text" }}
output = "Text"
template = "Summary of $text"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestInputsTemplateExamples:
    @pytest.mark.parametrize(
        ("pipe_code", "expected_examples"),
        [
            pytest.param(None, ["examples/demo.json"], id="the_main_pipe"),
            pytest.param("alpha.summarize", ["examples/demo.json"], id="the_main_pipe_named"),
            pytest.param("beta.summarize", None, id="a_pipe_of_the_same_code_in_another_domain"),
        ],
    )
    async def test_examples_are_offered_beside_the_main_pipe_of_the_bundle_s_own_tree_only(
        self, tmp_path: Path, pipe_code: str | None, expected_examples: list[str] | None
    ) -> None:
        """The manifest's `main_pipe` is the pipe of its code the bundle's own domain defines: a pipe of the same code in
        another domain, loaded from a library directory, is not offered the examples.
        """
        package_dir = tmp_path / "package"
        package_dir.mkdir()
        (package_dir / "METHODS.toml").write_text(_MANIFEST, encoding="utf-8")
        (package_dir / "alpha.mthds").write_text(_bundle("alpha"), encoding="utf-8")
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        (other_dir / "beta.mthds").write_text(_bundle("beta"), encoding="utf-8")

        try:
            result = await build_inputs_for_pipe(bundle_path=package_dir / "alpha.mthds", pipe_code=pipe_code, library_dirs=[other_dir])
        finally:
            library_id = get_current_library_id_or_none()
            if library_id is not None:
                get_library_manager().teardown(library_id=library_id)
            clear_current_library()

        assert result.get("examples") == expected_examples
