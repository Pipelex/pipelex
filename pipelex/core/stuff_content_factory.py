from typing import Any, Dict, Type

from pipelex.core.stuff_content import StuffContent, TextContent
from pipelex.exceptions import PipelexError
from pipelex.hub import get_class_registry, get_required_concept


class StuffContentFactoryError(PipelexError):
    pass


class StuffContentFactory:
    @classmethod
    def make_content_from_value(cls, stuff_content_subclass: Type[StuffContent], value: Dict[str, Any] | str) -> StuffContent:
        if isinstance(value, str) and stuff_content_subclass == TextContent:
            return TextContent(text=value)
        return stuff_content_subclass.model_validate(obj=value)

    @classmethod
    def make_stuffcontent_from_concept_code_required(cls, concept_code: str, value: Dict[str, Any] | str) -> StuffContent:
        """
        Create StuffContent from concept code, requiring the concept to be linked to a class in the registry.
        Raises StuffContentFactoryError if no registry class is found.
        """
        concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_class(name=the_subclass_name)

        if the_subclass is None:
            raise StuffContentFactoryError(f"Concept '{concept_code}' requires class '{the_subclass_name}' to be registered in the class registry")

        if not issubclass(the_subclass, StuffContent):
            raise StuffContentFactoryError(f"Concept '{concept_code}', subclass '{the_subclass}' is not a subclass of StuffContent")

        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)

    @classmethod
    def make_stuffcontent_from_concept_code_with_fallback(cls, concept_code: str, value: Dict[str, Any] | str) -> StuffContent:
        """
        Create StuffContent from concept code, falling back to TextContent if no registry class is found.
        """
        concept = get_required_concept(concept_code=concept_code)
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_class(name=the_subclass_name)

        if the_subclass is None:
            return cls.make_content_from_value(stuff_content_subclass=TextContent, value=value)

        if not issubclass(the_subclass, StuffContent):
            raise StuffContentFactoryError(f"Concept '{concept_code}', subclass '{the_subclass}' is not a subclass of StuffContent")

        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)
