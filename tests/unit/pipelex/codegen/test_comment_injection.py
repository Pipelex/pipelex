from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.codegen.emitters.target import CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.codegen.exceptions import CodegenEmissionError
from tests.unit.pipelex.codegen.comment_injection_poc import (
    LINE_BREAKS,
    NESTED_POSITIONS,
    PYTHON_TARGETS,
    code_names,
    crate_around_validation,
    import_emitted,
    poc_payload,
)


def _one_comment_line(text: str) -> list[str]:
    """`comment_lines` as it was before the fix: the whole text as a single comment line, line breaks and all."""
    return [text]


class TestEmittedModuleBehindTheLoadRefusal:
    """A name that reaches an emitter around the load refusal still lands in a comment, never in code."""

    @pytest.mark.parametrize("line_break", LINE_BREAKS)
    @pytest.mark.parametrize("position", NESTED_POSITIONS)
    @pytest.mark.parametrize("target", PYTHON_TARGETS)
    def test_proof_of_concept_name_stays_inside_the_comment(self, tmp_path: Path, target: CodegenTarget, position: str, line_break: str):
        """The reason quotes the name with `repr`, so the comment holds its escape and importing the module runs nothing."""
        marker = tmp_path / "MARKER"
        crate = crate_around_validation(position=position, type_name=poc_payload(line_break=line_break, marker=marker))

        (emitted,) = emit_types(crate, target=target)

        imprecise_lines = [line for line in emitted.content.splitlines() if "# imprecise:" in line]
        assert len(imprecise_lines) == 1
        assert f"{line_break!r}"[1:-1] in imprecise_lines[0]
        assert "__import__" not in code_names(emitted.content)
        import_emitted(content=emitted.content, module_name=f"poc_{target.replace('-', '_')}")
        assert not marker.exists()

    @pytest.mark.parametrize("line_break", LINE_BREAKS)
    @pytest.mark.parametrize("target", PYTHON_TARGETS)
    def test_a_line_break_in_a_reason_is_written_one_comment_line_each(
        self, tmp_path: Path, mocker: MockerFixture, target: CodegenTarget, line_break: str
    ):
        """A reason that does hold a line break is split, each line led by its own `#`, so no line of it reads as code."""
        marker = tmp_path / "MARKER"
        payload = poc_payload(line_break=line_break, marker=marker)
        mocker.patch("pipelex.codegen.emitters.python_common.iter_imprecision_reasons", return_value=[payload])
        crate = crate_around_validation(position="item_type", type_name="Any")

        (emitted,) = emit_types(crate, target=target)

        assert "__import__" not in code_names(emitted.content)
        injected_lines = [line for line in emitted.content.splitlines() if "__import__" in line]
        assert injected_lines == ["    #     __import__('pathlib').Path(" + repr(str(marker)) + ").write_text('pwned')"]
        import_emitted(content=emitted.content, module_name=f"poc_split_{target.replace('-', '_')}")
        assert not marker.exists()

    @pytest.mark.parametrize("line_break", LINE_BREAKS)
    @pytest.mark.parametrize("target", PYTHON_TARGETS)
    def test_the_shape_gate_refuses_a_module_a_reason_broke_out_of(
        self, tmp_path: Path, mocker: MockerFixture, target: CodegenTarget, line_break: str
    ):
        """With the comment written as one line again, the injected statement is refused by the shape gate, never returned."""
        marker = tmp_path / "MARKER"
        mocker.patch(
            "pipelex.codegen.emitters.python_common.iter_imprecision_reasons", return_value=[poc_payload(line_break=line_break, marker=marker)]
        )
        mocker.patch("pipelex.codegen.emitters.python_common.comment_lines", side_effect=_one_comment_line)
        crate = crate_around_validation(position="item_type", type_name="Any")

        with pytest.raises(CodegenEmissionError, match="other than its docstring and its fields"):
            emit_types(crate, target=target)

        assert not marker.exists()
