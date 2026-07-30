from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.interpreter_hub import get_concept_library
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from tests.unit.pipelex.builder.pipe.pipe_operator.pipe_llm.test_data import PipeLLMTestCases


class TestPipeLLMBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeLLMTestCases.TEST_CASES,
    )
    def test_pipe_llm_spec_to_blueprint(
        self, test_name: str, pipe_spec: PipeLLMSpec, expected_blueprint: PipeLLMBlueprint, load_empty_library: Callable[[], str]
    ):
        load_empty_library()
        # Built from blueprints, not `ConceptFactory.make`: the blueprint path materializes and
        # registers each structure class, so the library reaches a state the loader could actually
        # produce. Naming a structure class that no registry holds is not a state a real library
        # can be in, and compatibility questions about it have no answer.
        item_concept = ConceptFactory.make_from_blueprint(concept_code="Item", domain_code="test_domain", blueprint_or_string_description="Item")
        data_concept = ConceptFactory.make_from_blueprint(concept_code="Data", domain_code="test_domain", blueprint_or_string_description="Data")
        analysis_concept = ConceptFactory.make_from_blueprint(
            concept_code="Analysis", domain_code="test_domain", blueprint_or_string_description="Analysis"
        )
        concept_library = get_concept_library()
        concept_library.add_new_concept(concept=item_concept)
        concept_library.add_new_concept(concept=data_concept)
        concept_library.add_new_concept(concept=analysis_concept)

        blueprint = pipe_spec.to_blueprint()
        assert blueprint == expected_blueprint

        pipe_llm = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="test_domain",
            pipe_code=f"test_pipe_{test_name}",
            blueprint=blueprint,
            concept_codes_from_the_same_domain=[data_concept.code, item_concept.code, analysis_concept.code],
        )
        pretty_print(pipe_llm, title="PipeLLM from blueprint")
