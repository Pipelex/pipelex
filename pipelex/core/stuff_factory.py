from typing import Any, Dict, List, Optional, Tuple

import shortuuid
from kajson.class_registry import class_registry
from pydantic import BaseModel, Field

from pipelex.config import get_config
from pipelex.core.concept import Concept, ConceptError
from pipelex.core.concept_code_factory import ConceptCodeFactory
from pipelex.core.concept_native import NativeConcept
from pipelex.core.stuff import Stuff, StuffCreationRecord
from pipelex.core.stuff_content import StuffContent, StuffContentInitableFromStr
from pipelex.exceptions import PipelexError
from pipelex.hub import get_required_concept


class StuffFactoryError(PipelexError):
    pass


class StuffBlueprint(BaseModel):
    name: str
    concept_code: str = Field(alias="concept")
    value: str


class StuffFactory:
    @classmethod
    def make_stuff_name(cls, concept_str: str) -> str:
        return Stuff.make_stuff_name(concept_str=concept_str)

    @classmethod
    def make_stuff(
        cls,
        concept_str: str,
        content: StuffContent,
        name: Optional[str] = None,
        code: Optional[str] = None,
        creation_record: Optional[StuffCreationRecord] = None,
        pipelex_session_id: Optional[str] = None,
    ) -> Stuff:
        try:
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=concept_str)
        except ConceptError:
            stuff_ref = name or code or "unnamed"
            raise StuffFactoryError(f"Concept '{concept_str}' does not contain a domain, could not make stuff '{stuff_ref}'")
        if not name:
            name = cls.make_stuff_name(concept_code)
        return Stuff(
            concept_code=concept_code,
            content=content,
            stuff_name=name,
            stuff_code=code or shortuuid.uuid()[:5],
            creation_record=creation_record,
            pipelex_session_id=pipelex_session_id or get_config().session_id,
        )

    @classmethod
    def make_stuff_using_concept(
        cls,
        concept: Concept,
        content: StuffContent,
        name: Optional[str] = None,
        code: Optional[str] = None,
        creation_record: Optional[StuffCreationRecord] = None,
        pipelex_session_id: Optional[str] = None,
    ) -> Stuff:
        if not name:
            name = cls.make_stuff_name(concept_str=concept.code)
        return Stuff(
            concept_code=concept.code,
            content=content,
            stuff_name=name,
            stuff_code=code or shortuuid.uuid()[:5],
            creation_record=creation_record,
            pipelex_session_id=pipelex_session_id or get_config().session_id,
        )

    @classmethod
    def make_from_blueprint_dict(cls, blueprint_dict: Dict[str, Any]) -> "Stuff":
        blueprint = StuffBlueprint.model_validate(obj=blueprint_dict)
        return cls.make_from_blueprint(blueprint=blueprint)

    @classmethod
    def make_from_blueprint_str(cls, blueprint_str: str) -> "Stuff":
        blueprint = StuffBlueprint.model_validate_json(json_data=blueprint_str)
        return cls.make_from_blueprint(blueprint=blueprint)

    @classmethod
    def make_from_blueprint(cls, blueprint: StuffBlueprint) -> "Stuff":
        the_stuff = cls.make_from_str(
            concept_str=blueprint.concept_code,
            str_value=blueprint.value,
            name=blueprint.name,
            pipelex_session_id="blueprint",
        )
        return the_stuff

    @classmethod
    def make_from_str(
        cls,
        str_value: str,
        name: Optional[str] = None,
        concept_str: str = NativeConcept.TEXT.code,
        pipelex_session_id: Optional[str] = None,
    ) -> Stuff:
        try:
            concept_code = ConceptCodeFactory.make_concept_code_from_str(concept_str=concept_str)
        except ConceptError:
            stuff_ref = name or "unnamed"
            raise StuffFactoryError(f"Concept '{concept_str}' does not contain a domain, could not make stuff '{stuff_ref}'")
        the_concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = the_concept.structure_class_name
        the_subclass = class_registry.get_class(name=the_subclass_name) or eval(the_subclass_name)
        if not issubclass(the_subclass, StuffContentInitableFromStr):
            raise StuffFactoryError(f"Concept '{concept_code}', subclass '{the_subclass}' is not InitableFromStr")
        stuff_content: StuffContent = the_subclass.make_from_str(str_value)

        if not name:
            name = cls.make_stuff_name(concept_str)

        return Stuff(
            concept_code=concept_str,
            content=stuff_content,
            stuff_name=name,
            stuff_code=shortuuid.uuid()[:5],
            creation_record=None,
            pipelex_session_id=pipelex_session_id or get_config().session_id,
        )

    @classmethod
    def make_multiple_text_from_str(cls, str_text_dict: Dict[str, str]) -> List[Stuff]:
        """
        Make multiple stuffs from a dictionary of strings.
        It is implied that each string value should be associated with a native.Text concept.
        """
        return [cls.make_from_str(concept_str=NativeConcept.TEXT.code, str_value=str_value, name=name) for name, str_value in str_text_dict.items()]

    @classmethod
    def make_multiple_stuff_from_str(cls, str_stuff_and_concepts_dict: Dict[str, Tuple[str, str]]) -> List[Stuff]:
        """
        Make multiple stuffs from a dictionary of strings.
        It is implied that each string value should be associated with a native.Text concept.
        """
        result: List[Stuff] = []
        for name, (concept_code, str_value) in str_stuff_and_concepts_dict.items():
            stuff = cls.make_from_str(concept_str=concept_code, str_value=str_value, name=name)
            result.append(stuff)
        return result

    @classmethod
    def combine_stuffs(cls, concept_code: str, stuff_contents: Dict[str, StuffContent], name: Optional[str] = None) -> Stuff:
        """
        Combine a dictionary of stuffs into a single stuff.
        """
        the_concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = the_concept.structure_class_name
        the_subclass = class_registry.get_required_subclass(name=the_subclass_name, base_class=StuffContent)
        the_stuff_content = the_subclass.model_validate(obj=stuff_contents)
        return cls.make_stuff(
            concept_str=concept_code,
            content=the_stuff_content,
            name=name,
        )
