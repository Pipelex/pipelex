from typing import Any

import pytest
from pydantic import BaseModel

from pipelex.codegen.emitters.python_structures import emit_python_structures
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.helpers import make_qualified_structure_class_name, normalize_structure_blueprint
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.library_crate import LibraryCrate
from tests.unit.pipelex.codegen.conftest import CRATE_TEST_VERSION, load_generated_module
from tests.unit.pipelex.core.concepts.structure_generation.cases import StructureParityCases

_CONCEPTS = StructureParityCases.CONCEPTS


def _class_name(concept_ref: str) -> str:
    parsed_ref = QualifiedRef.parse(concept_ref)
    assert parsed_ref.domain_path is not None
    return make_qualified_structure_class_name(domain_code=parsed_ref.domain_path, concept_code=parsed_ref.local_code)


@pytest.fixture(scope="module")
def emitted_classes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, type[BaseModel]]:
    """The classes of the module the `python-structures` emitter writes for the concepts, executed as a developer imports it."""
    crate = normalize_crate(LibraryCrate(concepts=dict[str, ConceptBlueprint | str](_CONCEPTS)), mthds_version=CRATE_TEST_VERSION)
    content = emit_python_structures(resolve_concepts_from_crate(crate).with_qualified_names())[0].content
    module = load_generated_module(content, tmp_path=tmp_path_factory.mktemp("parity"), name="gen_structures_create_model_parity")
    return {concept_ref: getattr(module, _class_name(concept_ref)) for concept_ref in _CONCEPTS}


@pytest.fixture(scope="module")
def built_classes() -> dict[str, type[BaseModel]]:
    """The classes the runtime structure generator builds for the concepts, rebuilt against each other as a library does."""
    classes: dict[str, type[BaseModel]] = {}
    for concept_ref, blueprint in _CONCEPTS.items():
        assert isinstance(blueprint.structure, dict)
        domain_code = QualifiedRef.parse(concept_ref).domain_path
        classes[concept_ref] = StructureGenerator(local_domain=domain_code).generate_from_structure_blueprint(
            class_name=_class_name(concept_ref),
            structure_blueprint=normalize_structure_blueprint(blueprint.structure),
            description=blueprint.description,
        )
    namespace: dict[str, Any] = {built_class.__name__: built_class for built_class in classes.values()}
    for built_class in classes.values():
        built_class.model_rebuild(_types_namespace=namespace)
    return classes


class TestStructureGeneratorParity:
    @pytest.mark.parametrize("concept_ref", list(_CONCEPTS))
    def test_the_built_class_has_the_schema_of_the_emitted_class(
        self, concept_ref: str, emitted_classes: dict[str, type[BaseModel]], built_classes: dict[str, type[BaseModel]]
    ):
        """The class built from data and the class the emitter writes as source give the same JSON schema."""
        built_class = built_classes[concept_ref]
        emitted_class = emitted_classes[concept_ref]

        assert built_class.__pydantic_complete__
        assert built_class.__bases__ == emitted_class.__bases__
        assert built_class.model_json_schema() == emitted_class.model_json_schema()
