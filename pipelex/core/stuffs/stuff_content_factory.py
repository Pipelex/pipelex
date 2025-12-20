from typing import Any

from pipelex.core.concepts.concept import Concept
from pipelex.core.stuffs.exceptions import StuffContentFactoryError
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_class_registry


class StuffContentFactory:
    @classmethod
    def make_content_from_value(cls, stuff_content_subclass: type[StuffContent], value: dict[str, Any] | str) -> StuffContent:
        if isinstance(value, str) and stuff_content_subclass == TextContent:
            return TextContent(text=value)
        return stuff_content_subclass.model_validate(obj=value)

    @classmethod
    def make_stuff_content_from_concept_required(cls, concept: Concept, value: dict[str, Any] | str) -> StuffContent:
        """Create StuffContent from concept code, requiring the concept to be linked to a class in the registry.
        Raises StuffContentFactoryError if no registry class is found.
        """
        the_subclass_name = concept.structure_class_name
        the_subclass = get_class_registry().get_required_subclass(name=the_subclass_name, base_class=StuffContent)
        return cls.make_content_from_value(stuff_content_subclass=the_subclass, value=value)

    @classmethod
    def make_stuff_content_from_concept_with_fallback(cls, concept: Concept, value: dict[str, Any] | str) -> StuffContent:
        """Create StuffContent from concept code, falling back to TextContent if no registry class is found."""
        the_structure_class = get_class_registry().get_class(name=concept.structure_class_name)

        if the_structure_class is None:
            return cls.make_content_from_value(stuff_content_subclass=TextContent, value=value)

        if not issubclass(the_structure_class, StuffContent):
            msg = f"Concept '{concept.code}', subclass '{the_structure_class}' is not a subclass of StuffContent"
            raise StuffContentFactoryError(msg)

        return cls.make_content_from_value(stuff_content_subclass=the_structure_class, value=value)
