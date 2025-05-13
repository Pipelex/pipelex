# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from inspect import getsource
from typing import Any, Dict, List, Optional, Type

from kajson.class_registry import class_registry
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pipelex.core.concept import Concept
from pipelex.core.stuff_content import TextContent
from pipelex.exceptions import ConceptFactoryError, StructureClassError


class ConceptBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: str
    structure: Optional[str] = None
    refines: List[str] = Field(default_factory=list)
    domain: Optional[str] = None


class ConceptFactory:
    @classmethod
    def make_refines(cls, domain: str, refines: List[str]) -> List[str]:
        new_refines: List[str] = []
        for ref in refines:
            if not Concept.concept_str_contains_domain(ref):
                ref = ConceptFactory.make_concept_code(domain=domain, code=ref)
            new_refines.append(ref)
        return new_refines

    @classmethod
    def make_concept_code(cls, domain: str, code: str) -> str:
        if "." in code:
            return code
        return f"{domain}.{code}"

    @classmethod
    def make_from_details_dict_if_possible(
        cls,
        domain: str,
        code: str,
        details_dict: Dict[str, Any],
    ) -> Optional[Concept]:
        if concept_definition := details_dict.pop("Concept", None):
            details_dict["definition"] = concept_definition
            details_dict["refines"] = ConceptFactory.make_refines(domain=domain, refines=details_dict.pop("refines", []))
            concept_blueprint = ConceptBlueprint.model_validate(details_dict)
            the_concept = ConceptFactory.make_concept_from_blueprint(domain=domain, code=code, concept_blueprint=concept_blueprint)
            return the_concept
        elif "definition" in details_dict:
            # legacy format
            details_dict["domain"] = domain
            details_dict["refines"] = ConceptFactory.make_refines(domain=domain, refines=details_dict.pop("refines", []))
            details_dict["code"] = ConceptFactory.make_concept_code(domain, code)
            try:
                the_concept = Concept.model_validate(details_dict)
            except ValidationError as e:
                raise ConceptFactoryError(f"Error validating concept: {e}") from e
            return the_concept
        else:
            return None

    @classmethod
    def make_from_details_dict(
        cls,
        domain_code: str,
        code: str,
        details_dict: Dict[str, Any],
    ) -> Concept:
        concept_definition = details_dict.pop("Concept", None)
        if not concept_definition:
            raise ConceptFactoryError(f"Concept '{code}' in domain '{domain_code}' has no definition")
        details_dict["definition"] = concept_definition
        details_dict["domain"] = domain_code
        details_dict["refines"] = ConceptFactory.make_refines(domain=domain_code, refines=details_dict.pop("refines", []))
        concept_blueprint = ConceptBlueprint.model_validate(details_dict)
        the_concept = ConceptFactory.make_concept_from_blueprint(domain=domain_code, code=code, concept_blueprint=concept_blueprint)
        return the_concept

    @classmethod
    def make_concept_from_definition(
        cls,
        domain_code: str,
        code: str,
        definition: str,
    ) -> Concept:
        structure_class_name: str
        if Concept.is_valid_structure_class(structure_class_name=code):
            # structure is set implicitly, by the concept's code
            structure_class_name = code
        else:
            structure_class_name = TextContent.__name__
        # TODO: why use a dict to create a concept? it makes no sense
        # TODO: don't wall make_concept_code from the factory, the code received here must already be a valid concept code
        concept_dict = {
            "domain": domain_code,
            "code": ConceptFactory.make_concept_code(domain_code, code),
            "definition": definition,
            "structure_class_name": structure_class_name,
        }
        try:
            the_concept = Concept.model_validate(concept_dict)
        except ValidationError as e:
            raise ConceptFactoryError(f"Error validating concept: {e}") from e
        return the_concept

    @classmethod
    def make_concept_from_blueprint(
        cls,
        domain: str,
        code: str,
        concept_blueprint: ConceptBlueprint,
    ) -> Concept:
        structure_class_name: str
        if structure := concept_blueprint.structure:
            # structure is set explicitly
            if not Concept.is_valid_structure_class(structure_class_name=structure):
                raise StructureClassError(
                    f"Structure class '{structure}' set for concept '{code}' in domain '{domain}' is not a registered subclass of StuffContent"
                )
            structure_class_name = structure
        elif Concept.is_valid_structure_class(structure_class_name=code):
            # structure is set implicitly, by the concept's code
            structure_class_name = code
        else:
            structure_class_name = TextContent.__name__

        return Concept(
            code=ConceptFactory.make_concept_code(domain, code),
            domain=domain,
            definition=concept_blueprint.definition,
            structure_class_name=structure_class_name,
            refines=concept_blueprint.refines,
        )

    @classmethod
    def get_concept_class_source_code(cls, concept_name: str, base_class: Type[Any]) -> str:
        if not class_registry.has_class(concept_name):
            raise RuntimeError(f"Class '{concept_name}' not found in registry")

        cls = class_registry.get_required_subclass(name=concept_name, base_class=base_class)
        return getsource(cls)
