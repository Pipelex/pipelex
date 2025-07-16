from typing import Any, Dict, List, Optional, Tuple, Type

import shortuuid
from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel

from pipelex import log
from pipelex.client.protocol import CompactMemory
from pipelex.core.concept_native import NativeConcept
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import ImageContent, PDFContent, StuffContent, TextContent
from pipelex.core.stuff_factory import StuffBlueprint, StuffContentFactory, StuffFactory
from pipelex.core.working_memory import MAIN_STUFF_NAME, StuffDict, WorkingMemory
from pipelex.exceptions import WorkingMemoryFactoryError
from pipelex.tools.misc.json_utils import load_json_dict_from_path


class WorkingMemoryFactory(BaseModel):
    @classmethod
    def make_from_text(
        cls,
        text: str,
        concept_str: str = NativeConcept.TEXT.code,
        name: Optional[str] = "text",
    ) -> WorkingMemory:
        stuff = StuffFactory.make_stuff(
            concept_str=concept_str,
            content=TextContent(text=text),
            name=name,
        )
        return cls.make_from_single_stuff(stuff=stuff)

    @classmethod
    def make_from_image(
        cls,
        image_url: str,
        concept_str: str = NativeConcept.IMAGE.code,
        name: Optional[str] = "image",
    ) -> WorkingMemory:
        stuff = StuffFactory.make_stuff(
            concept_str=concept_str,
            content=ImageContent(url=image_url),
            name=name,
        )
        return cls.make_from_single_stuff(stuff=stuff)

    @classmethod
    def make_from_pdf(
        cls,
        pdf_url: str,
        concept_str: str = NativeConcept.PDF.code,
        name: Optional[str] = "pdf",
    ) -> WorkingMemory:
        stuff = StuffFactory.make_stuff(
            concept_str=concept_str,
            content=PDFContent(url=pdf_url),
            name=name,
        )
        return cls.make_from_single_stuff(stuff=stuff)

    @classmethod
    def make_from_stuff_and_name(cls, stuff: Stuff, name: str) -> WorkingMemory:
        stuff_dict: StuffDict = {name: stuff}
        aliases: Dict[str, str] = {MAIN_STUFF_NAME: name}
        return WorkingMemory(root=stuff_dict, aliases=aliases)

    @classmethod
    def make_from_single_blueprint(cls, blueprint: StuffBlueprint) -> WorkingMemory:
        stuff = StuffFactory.make_from_blueprint(blueprint=blueprint)
        return cls.make_from_single_stuff(stuff=stuff)

    @classmethod
    def make_from_single_stuff(cls, stuff: Stuff) -> WorkingMemory:
        name = stuff.stuff_name
        if not name:
            raise WorkingMemoryFactoryError(f"Cannot make_from_single_stuff because stuff has no name: {stuff}")
        return cls.make_from_stuff_and_name(stuff=stuff, name=name)

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
        stuff_dict: StuffDict = {}
        for name, content in input_dict.items():
            if not isinstance(content, str):
                continue
            text_content = TextContent(text=content)
            stuff_dict[name] = Stuff(
                stuff_name=name,
                stuff_code="",
                concept_code=NativeConcept.TEXT.code,
                content=text_content,
            )
        return WorkingMemory(root=stuff_dict)

    @classmethod
    def make_empty(cls) -> WorkingMemory:
        return WorkingMemory(root={})

    @classmethod
    def make_from_memory_file(cls, memory_file_path: str) -> WorkingMemory:
        working_memory_dict = load_json_dict_from_path(memory_file_path)
        working_memory = WorkingMemory.model_validate(working_memory_dict)
        return working_memory

    @classmethod
    def make_from_compact_memory(cls, compact_memory: CompactMemory) -> WorkingMemory:
        """
        Create a WorkingMemory from a compact memory dictionary.

        Args:
            compact_memory: Dictionary in the format from API serialization

        Returns:
            WorkingMemory object reconstructed from the compact format
        """
        working_memory = cls.make_empty()

        for stuff_key, stuff_data in compact_memory.items():
            concept_code = stuff_data.get("concept_code", "")
            content_value = stuff_data.get("content", {})

            content = StuffContentFactory.make_stuffcontent_from_concept_code_with_fallback(concept_code=concept_code, value=content_value)

            stuff = StuffFactory.make_stuff(concept_str=concept_code, name=stuff_key, content=content)

            working_memory.add_new_stuff(name=stuff_key, stuff=stuff)

        return working_memory

    @classmethod
    def make_for_dry_run(cls, needed_inputs: List[Tuple[str, str, Type[StuffContent]]]) -> "WorkingMemory":
        """
        Create a WorkingMemory with mock objects for dry run mode.

        Args:
            needed_inputs: List of tuples (stuff_name, concept_code, structure_class)

        Returns:
            WorkingMemory with mock objects for each needed input
        """

        working_memory = cls.make_empty()

        for variable_name, concept_code, structure_class in needed_inputs:
            log.debug(f"Creating dry run mock for '{variable_name}' with concept '{concept_code}' and class '{structure_class.__name__}'")

            try:
                if structure_class:
                    # Create mock object using polyfactory
                    class MockFactory(ModelFactory[structure_class]):  # type: ignore
                        __model__ = structure_class
                        __check_model__ = True
                        __use_examples__ = True
                        __allow_none_optionals__ = False  # Ensure Optional fields always get values

                    mock_content = MockFactory.build()
                else:
                    # Fallback to text content
                    mock_content = TextContent(text=f"DRY RUN: Mock content for '{variable_name}' ({concept_code})")

                # Create stuff with mock content
                mock_stuff = Stuff(
                    stuff_name=variable_name,
                    stuff_code=shortuuid.uuid()[:5],
                    concept_code=concept_code,
                    content=mock_content,
                )

                working_memory.add_new_stuff(name=variable_name, stuff=mock_stuff)

            except Exception as e:
                log.warning(f"Failed to create mock for '{variable_name}' ({concept_code}): {e}. Using fallback text content.")
                # Create fallback text content
                fallback_content = TextContent(text=f"DRY RUN: Fallback mock for '{variable_name}' ({concept_code})")
                fallback_stuff = Stuff(
                    stuff_name=variable_name,
                    stuff_code=shortuuid.uuid()[:5],
                    concept_code=concept_code,
                    content=fallback_content,
                )
                working_memory.add_new_stuff(name=variable_name, stuff=fallback_stuff)

        return working_memory
