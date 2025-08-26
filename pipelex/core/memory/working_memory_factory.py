from typing import Any, Dict, List, Optional, cast

import shortuuid
from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel

from pipelex import log
from pipelex.client.protocol import CompactMemory, ImplicitMemory
from pipelex.core.concepts.concept import ConceptBlueprint, SpecialDomain
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, StuffDict, WorkingMemory
from pipelex.core.pipes.pipe_input_spec import TypedNamedInputRequirement
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import ImageContent, ListContent, PDFContent, StuffContent, TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.exceptions import WorkingMemoryFactoryError
from pipelex.hub import get_required_concept


class WorkingMemoryFactory(BaseModel):
    @classmethod
    def make_from_text(
        cls,
        text: str,
        concept_string: str = SpecialDomain.NATIVE.value + "." + NativeConceptEnum.TEXT.value,
        name: Optional[str] = "text",
    ) -> WorkingMemory:
        ConceptBlueprint.validate_concept_string(concept_string=concept_string)
        return cls.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_required_concept(concept_string=concept_string),
                content=TextContent(text=text),
                name=name,
            )
        )

    @classmethod
    def make_from_image(
        cls,
        image_url: str,
        concept_string: str = SpecialDomain.NATIVE.value + "." + NativeConceptEnum.IMAGE.value,
        name: Optional[str] = "image",
    ) -> WorkingMemory:
        # TODO: validate that the concept is compatible with an image concept
        ConceptBlueprint.validate_concept_string(concept_string=concept_string)
        stuff = StuffFactory.make_stuff(
            concept=get_required_concept(concept_string=concept_string),
            content=ImageContent(url=image_url),
            name=name,
        )
        return cls.make_from_single_stuff(stuff=stuff)

    @classmethod
    def make_from_pdf(
        cls,
        pdf_url: str,
        concept_string: str = SpecialDomain.NATIVE.value + "." + NativeConceptEnum.PDF.value,
        name: Optional[str] = "pdf",
    ) -> WorkingMemory:
        ConceptBlueprint.validate_concept_string(concept_string=concept_string)
        return cls.make_from_single_stuff(
            stuff=StuffFactory.make_stuff(
                concept=get_required_concept(concept_string=concept_string),
                content=PDFContent(url=pdf_url),
                name=name,
            )
        )

    @classmethod
    def make_from_single_stuff(cls, stuff: Stuff) -> WorkingMemory:
        if not stuff.stuff_name:
            raise WorkingMemoryFactoryError(f"Cannot make_from_single_stuff because stuff has no name: {stuff}")
        stuff_dict: StuffDict = {stuff.stuff_name: stuff}
        return WorkingMemory(root=stuff_dict, aliases={MAIN_STUFF_NAME: stuff.stuff_name})

    @classmethod
    def make_from_multiple_stuffs(
        cls,
        stuff_list: List[Stuff],
        main_name: Optional[str] = None,
        is_ignore_unnamed: bool = False,
    ) -> WorkingMemory:
        stuff_dict: StuffDict = {}
        for stuff in stuff_list:
            name = stuff.stuff_name
            if not name:
                if is_ignore_unnamed:
                    continue
                else:
                    raise WorkingMemoryFactoryError(f"Stuff {stuff} has no name")
            stuff_dict[name] = stuff
        aliases: Dict[str, str] = {}
        if stuff_dict:
            if main_name:
                aliases[MAIN_STUFF_NAME] = main_name
            else:
                aliases[MAIN_STUFF_NAME] = list(stuff_dict.keys())[0]
        return WorkingMemory(root=stuff_dict, aliases=aliases)

    @classmethod
    def make_from_strings_from_dict(cls, input_dict: Dict[str, Any]) -> WorkingMemory:
        # TODO: Add unit tests for this method
        stuff_dict: StuffDict = {}
        for name, content in input_dict.items():
            if not isinstance(content, str):
                continue
            text_content = TextContent(text=content)
            stuff_dict[name] = StuffFactory.make_stuff(
                concept=get_required_concept(concept_string=SpecialDomain.NATIVE.value + "." + NativeConceptEnum.TEXT.value),
                content=text_content,
                name=name,
                code="",
            )
        return WorkingMemory(root=stuff_dict)

    @classmethod
    def make_empty(cls) -> WorkingMemory:
        return WorkingMemory(root={})

    @classmethod
    def make_from_compact_memory(
        cls,
        compact_memory: CompactMemory,
        search_domains: Optional[List[str]] = None,
    ) -> WorkingMemory:
        implicit_memory = cast(ImplicitMemory, compact_memory)
        return cls.make_from_implicit_memory(
            implicit_memory=implicit_memory,
            search_domains=search_domains,
        )

    @classmethod
    def make_from_implicit_memory(
        cls,
        implicit_memory: ImplicitMemory,
        search_domains: Optional[List[str]] = None,
    ) -> WorkingMemory:
        """
        Create a WorkingMemory from a compact memory dictionary.

        Args:
            compact_memory: Dictionary in the format from API serialization

        Returns:
            WorkingMemory object reconstructed from the compact format
        """
        working_memory = cls.make_empty()

        for stuff_key, stuff_content_or_data in implicit_memory.items():
            stuff = StuffFactory.make_stuff_from_stuff_content_using_search_domains(
                name=stuff_key,
                stuff_content_or_data=stuff_content_or_data,
                search_domains=search_domains or [],
            )

            working_memory.add_new_stuff(name=stuff_key, stuff=stuff)

        return working_memory

    @classmethod
    def create_mock_content(cls, requirement: TypedNamedInputRequirement) -> StuffContent:
        """Helper method to create mock content for a requirement."""
        if requirement.structure_class:
            # Create mock object using polyfactory
            class MockFactory(ModelFactory[requirement.structure_class]):  # type: ignore
                __model__ = requirement.structure_class
                __check_model__ = True
                __use_examples__ = True
                __allow_none_optionals__ = False  # Ensure Optional fields always get values

            return MockFactory.build()  # type: ignore
        else:
            # Fallback to text content
            return TextContent(text=f"DRY RUN: Mock content for '{requirement.variable_name}' ({requirement.concept.code})")

    @classmethod
    def make_for_dry_run(cls, needed_inputs: List[TypedNamedInputRequirement]) -> "WorkingMemory":
        """
        Create a WorkingMemory with mock objects for dry run mode.

        Args:
            needed_inputs: List of tuples (stuff_name, concept_code, structure_class)

        Returns:
            WorkingMemory with mock objects for each needed input
        """
        working_memory = cls.make_empty()

        for requirement in needed_inputs:
            log.debug(
                f"Creating dry run mock for '{requirement.variable_name}' with concept "
                f"'{requirement.concept.code}' and class '{requirement.structure_class.__name__}'"
            )

            try:
                if not requirement.multiplicity:
                    mock_content = cls.create_mock_content(requirement)

                    # Create stuff with mock content
                    mock_stuff = StuffFactory.make_stuff(
                        concept=requirement.concept,
                        content=mock_content,
                        name=requirement.variable_name,
                        code=shortuuid.uuid()[:5],
                    )

                    working_memory.add_new_stuff(name=requirement.variable_name, stuff=mock_stuff)
                else:
                    # Let's create a ListContent of multiple stuffs
                    nb_stuffs: int
                    if isinstance(requirement.multiplicity, bool):
                        # TODO: make this configurable or use existing config variable
                        nb_stuffs = 3
                    else:
                        nb_stuffs = requirement.multiplicity

                    items: List[StuffContent] = []
                    for _ in range(nb_stuffs):
                        item_mock_content = cls.create_mock_content(requirement)
                        items.append(item_mock_content)

                    mock_list_content = ListContent[StuffContent](items=items)

                    # Create stuff with mock content
                    mock_stuff = StuffFactory.make_stuff(
                        concept=requirement.concept,
                        content=mock_list_content,
                        name=requirement.variable_name,
                        code=shortuuid.uuid()[:5],
                    )

                    working_memory.add_new_stuff(name=requirement.variable_name, stuff=mock_stuff)

            except Exception as exc:
                log.warning(
                    f"Failed to create mock for '{requirement.variable_name}' ({requirement.concept.code}): {exc}. Using fallback text content."
                )
                # Create fallback text content
                fallback_content = TextContent(text=f"DRY RUN: Fallback mock for '{requirement.variable_name}' ({requirement.concept.code})")
                fallback_stuff = StuffFactory.make_stuff(
                    concept=requirement.concept,
                    content=fallback_content,
                    name=requirement.variable_name,
                    code=shortuuid.uuid()[:5],
                )
                working_memory.add_new_stuff(name=requirement.variable_name, stuff=fallback_stuff)

        return working_memory
