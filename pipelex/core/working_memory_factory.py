# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from pipelex.core.concept_native import NativeConcept
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import ImageContent, PDFContent, TextContent
from pipelex.core.stuff_factory import StuffBlueprint, StuffFactory
from pipelex.core.working_memory import MAIN_STUFF_NAME, StuffDict, WorkingMemory
from pipelex.exceptions import WorkingMemoryError
from pipelex.tools.utils.json_utils import load_json_dict_from_path


class WorkingMemoryFactory(BaseModel):
    @classmethod
    def make_from_text(
        cls,
        text: str,
        concept_code: str = NativeConcept.TEXT.code,
        name: Optional[str] = "text",
    ) -> WorkingMemory:
        stuff = StuffFactory.make_stuff(
            concept_code=concept_code,
            content=TextContent(text=text),
            name=name,
        )
        return cls.make_from_single_stuff(stuff=stuff)

    @classmethod
    def make_from_image(
        cls,
        image_url: str,
        concept_code: str = NativeConcept.IMAGE.code,
        name: Optional[str] = "image",
    ) -> WorkingMemory:
        stuff = StuffFactory.make_stuff(
            concept_code=concept_code,
            content=ImageContent(url=image_url),
            name=name,
        )
        return cls.make_from_single_stuff(stuff=stuff)

    @classmethod
    def make_from_pdf(
        cls,
        pdf_url: str,
        concept_code: str = NativeConcept.PDF.code,
        name: Optional[str] = "pdf",
    ) -> WorkingMemory:
        stuff = StuffFactory.make_stuff(
            concept_code=concept_code,
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
            raise WorkingMemoryError(f"Cannot make_from_single_stuff because stuff has no name: {stuff}")
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
                    raise WorkingMemoryError(f"Stuff {stuff} has no name")
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
