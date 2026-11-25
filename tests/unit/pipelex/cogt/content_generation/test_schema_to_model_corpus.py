from typing import Any

import pytest
from pydantic import BaseModel

from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.system.registries.class_registry_access import get_class_registry
from tests.unit.pipelex.cogt.content_generation.cases import SchemaRebuildTestData

_CORPUS_DOMAIN = "schema_rebuild_corpus"

_NATIVE_CLASSES: list[type[BaseModel]] = [code.structure_class for code in NativeConceptCode if code.structure_class is not None]


def _assert_rebuilds_exactly(*, original_schema: dict[str, Any], class_name: str) -> None:
    rebuilt = SchemaToModelFactory.make_from_json_schema(original_schema, class_name=class_name)
    assert rebuilt.model_json_schema() == original_schema


class TestSchemaToModelCorpus:
    @pytest.mark.parametrize("model_class", _NATIVE_CLASSES + SchemaRebuildTestData.MODEL_CLASSES, ids=lambda model_class: model_class.__name__)
    def test_a_model_class_rebuilds_into_its_own_schema(self, model_class: type[BaseModel]) -> None:
        """The class rebuilt from a native content class's schema, or from one of every supported shape, has that schema."""
        _assert_rebuilds_exactly(original_schema=model_class.model_json_schema(), class_name=model_class.__name__)

    @pytest.mark.parametrize(("concept_code", "blueprint"), SchemaRebuildTestData.STRUCTURE_BLUEPRINTS)
    def test_a_concept_structure_rebuilds_into_its_own_schema(self, concept_code: str, blueprint: ConceptBlueprint) -> None:
        """The class rebuilt from the schema of a concept's structure class, as a method declares it, has that schema."""
        concept = ConceptFactory.make_from_blueprint(domain_code=_CORPUS_DOMAIN, concept_code=concept_code, blueprint_or_string_description=blueprint)
        structure_class = get_class_registry().get_required_subclass(name=concept.structure_class_name, base_class=BaseModel)

        _assert_rebuilds_exactly(original_schema=structure_class.model_json_schema(), class_name=structure_class.__name__)
