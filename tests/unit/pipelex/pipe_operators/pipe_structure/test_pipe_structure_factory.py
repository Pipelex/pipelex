from typing import Callable

import pytest

from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.pipe_operators.structure.pipe_structure import PipeStructure
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestPipeStructureFactory:
    @pytest.mark.parametrize(
        ("test_id", "output_str", "expected_multiplicity"),
        [
            ("single", "native.Number", None),
            ("variable_list", "native.Number[]", True),
            ("fixed_count", "native.Number[3]", 3),
        ],
    )
    def test_factory_resolves_output_multiplicity(
        self,
        test_id: str,
        output_str: str,
        expected_multiplicity: int | bool | None,
        load_empty_library: Callable[[], str],
    ) -> None:
        load_empty_library()
        blueprint = PipeStructureBlueprint(
            description="Structure draft text",
            inputs={"draft_text": "native.Text"},
            output=output_str,
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=f"struct_{test_id}",
            blueprint=blueprint,
        )

        assert pipe_structure.text_input_name == "draft_text"
        assert pipe_structure.output_multiplicity == expected_multiplicity
        assert pipe_structure.code == f"struct_{test_id}"

    def test_factory_default_model_choice_is_none(self, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()
        blueprint = PipeStructureBlueprint(
            description="Structure draft text",
            inputs={"draft_text": "native.Text"},
            output="native.Number",
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_domain",
            pipe_code="struct_no_model",
            blueprint=blueprint,
        )
        assert pipe_structure.llm_choice is None

    def test_long_pipe_code(self, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()
        long_pipe_code = "a" + "_b" * 30  # ~63 chars, snake_case
        blueprint = PipeStructureBlueprint(
            description="Structure draft text",
            inputs={"draft_text": "native.Text"},
            output="native.Number",
        )
        pipe_structure: PipeStructure = PipeFactory[PipeStructure].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=long_pipe_code,
            blueprint=blueprint,
        )
        assert pipe_structure.code == long_pipe_code
