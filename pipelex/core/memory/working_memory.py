from operator import attrgetter
from typing import Any, Dict, List, Optional, Set, Type

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self, override

from pipelex import log, pretty_print
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_content import (
    HtmlContent,
    ImageContent,
    ListContent,
    MermaidContent,
    NumberContent,
    PDFContent,
    StuffContentType,
    TextAndImagesContent,
    TextContent,
)
from pipelex.exceptions import (
    WorkingMemoryConsistencyError,
    WorkingMemoryStuffAttributeNotFoundError,
    WorkingMemoryStuffNotFoundError,
    WorkingMemoryTypeError,
)
from pipelex.tools.misc.context_provider_abstract import ContextProviderAbstract

MAIN_STUFF_NAME = "main_stuff"
BATCH_ITEM_STUFF_NAME = "BATCH_ITEM"
PRETTY_PRINT_MAX_LENGTH = 1000

StuffDict = Dict[str, Stuff]
StuffArtefactDict = Dict[str, StuffArtefact]


class WorkingMemory(BaseModel, ContextProviderAbstract):
    root: StuffDict = Field(default_factory=dict)
    aliases: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_stuff_names(self) -> Self:
        for key, stuff in self.root.items():
            if key.startswith("_") and not key == BATCH_ITEM_STUFF_NAME:
                log.warning(f"Stuff key '{key}' starts with '_', which is reserved for params")

            if not stuff.stuff_name:
                self.root[key].stuff_name = key
            elif key != MAIN_STUFF_NAME and stuff.stuff_name != key:
                log.warning(f"Stuff name '{stuff.stuff_name}' does not match the key '{key}'")
            elif stuff.stuff_name.startswith("_") and stuff.stuff_name != BATCH_ITEM_STUFF_NAME:
                log.warning(f"Stuff name '{stuff.stuff_name}' starts with '_', which is reserved for params")

        return self

    def pretty_print_summary(self):
        for stuff in self.root.values():
            content = stuff.content.rendered_plain()
            if len(content) > PRETTY_PRINT_MAX_LENGTH:
                content = content[:PRETTY_PRINT_MAX_LENGTH] + "..."
            pretty_print(content, title=f"{stuff.stuff_name} ({stuff.concept.code})")

    def make_deep_copy(self) -> Self:
        return self.model_copy(deep=True)

    def get_optional_stuff(self, name: str) -> Optional[Stuff]:
        if named_stuff := self.root.get(name):
            return named_stuff
        if alias := self.aliases.get(name):
            return self.root.get(alias)
        return None

    def get_optional_main_stuff(self) -> Optional[Stuff]:
        return self.get_optional_stuff(name=MAIN_STUFF_NAME)

    # TODO: all calls to get_stuff should catch WorkingMemoryStuffNotFoundError in order to indicate what pipe is missing a required stuff
    def get_stuff(self, name: str) -> Stuff:
        if named_stuff := self.root.get(name):
            return named_stuff
        if alias := self.aliases.get(name):
            stuff = self.root.get(alias)
            if stuff is None:
                raise WorkingMemoryStuffNotFoundError(
                    variable_name=alias,
                    message=f"Alias '{alias}' points to a non-existent stuff '{name}'",
                )
            return stuff
        raise WorkingMemoryStuffNotFoundError(
            variable_name=name,
            message=f"Stuff '{name}' not found in working memory, valid keys are: {self.list_keys()}",
        )

    def get_stuffs(self, names: Set[str]) -> List[Stuff]:
        the_stuffs: List[Stuff] = []
        for name in names:
            the_stuffs.append(self.get_stuff(name=name))
        return the_stuffs

    def get_existing_stuffs(self, names: Set[str]) -> List[Stuff]:
        the_stuffs: List[Stuff] = []
        for name in names:
            if stuff := self.get_optional_stuff(name=name):
                the_stuffs.append(stuff)
        return the_stuffs

    def is_stuff_code_used(self, stuff_code: str) -> bool:
        for stuff in self.root.values():
            if stuff.concept.code == stuff_code:
                return True
        return False

    def get_main_stuff(self) -> Stuff:
        return self.get_stuff(name=MAIN_STUFF_NAME)

    def remove_stuff(self, name: str):
        self.root.pop(name, None)

    def remove_main_stuff(self):
        if MAIN_STUFF_NAME in self.root:
            del self.root[MAIN_STUFF_NAME]

    def set_stuff(self, name: str, stuff: Stuff):
        self.root[name] = stuff

    def add_new_stuff(self, name: str, stuff: Stuff, aliases: Optional[List[str]] = None):
        # TODO: Add unit tests for this method
        log.debug(f"Adding new stuff '{name}' to WorkingMemory with aliases: {aliases}")
        if self.is_stuff_code_used(stuff_code=stuff.stuff_code):
            raise WorkingMemoryConsistencyError(f"Stuff code '{stuff.stuff_code}' is already used by another stuff")
        if name in self.root or name in self.aliases:
            existing_stuff = self.get_stuff(name=name)
            if existing_stuff == stuff:
                log.warning(f"Key '{name}' already exists in WorkingMemory with the same stuff")
                return
            else:
                log.warning(f"Key '{name}' already exists in WorkingMemory and will be replaced by something different")
                log.verbose(f"Existing stuff: {existing_stuff}")
                log.verbose(f"New stuff: {stuff}")

        # it's a new stuff
        self.set_stuff(name=name, stuff=stuff)
        if aliases:
            for alias in aliases:
                self.set_alias(alias, name)

    def set_new_main_stuff(self, stuff: Stuff, name: Optional[str] = None):
        # TODO: Add unit tests for this method
        if name:
            self.remove_main_stuff()
            self.add_new_stuff(name=name, stuff=stuff, aliases=[MAIN_STUFF_NAME])
            log.verbose(f"Setting new main stuff {name}: {stuff.concept.code} = '{stuff.short_desc}'")
            log.verbose(stuff.content.rendered_plain())
        else:
            self.remove_alias_to_main_stuff()
            self.set_stuff(name=MAIN_STUFF_NAME, stuff=stuff)
            log.verbose(f"Setting new main stuff (unnamed): {stuff.concept.code} = '{stuff.short_desc}'")

    def set_alias(self, alias: str, target: str) -> None:
        """Add an alias pointing to a target name."""
        if alias == target:
            raise WorkingMemoryConsistencyError(f"Cannot create alias '{alias}' pointing to itself")
        if target not in self.root:
            raise WorkingMemoryConsistencyError(f"Cannot create alias to non-existent target '{target}'")
        log.debug(f"Setting alias '{alias}' pointing to target '{target}'")
        self.aliases[alias] = target

    def add_alias(self, alias: str, target: str) -> None:
        """Add an alias pointing to a target name."""
        if alias in self.root:
            raise WorkingMemoryConsistencyError(f"Cannot add alias '{alias}' as it already exists")
        self.set_alias(alias=alias, target=target)
        log.debug(f"Added alias '{alias}' pointing to target '{target}'")

    def remove_alias(self, alias: str) -> None:
        """Remove an alias if it exists."""
        if alias in self.aliases:
            del self.aliases[alias]

    def remove_alias_to_main_stuff(self) -> None:
        """Remove the alias pointing to the main stuff if it exists."""
        self.remove_alias(alias=MAIN_STUFF_NAME)

    def get_aliases_for(self, target: str) -> List[str]:
        """Get all aliases pointing to a target name."""
        return [alias for alias, t in self.aliases.items() if t == target]

    def list_keys(self) -> List[str]:
        return list(self.root.keys()) + list(self.aliases.keys())

    def pretty_print(self):
        for name, stuff in self.root.items():
            pretty_print(stuff.content.rendered_plain(), title=f"{name}: {stuff.concept.code}")

    ################################################################################################
    # ContextProviderAbstract
    ################################################################################################

    @override
    def generate_context(self) -> Dict[str, Any]:
        # TODO: Add unit tests for this method
        artefact_dict: StuffArtefactDict = {}
        for name, stuff in self.root.items():
            a = stuff.make_artefact()
            artefact_dict[name] = a
        for alias, target in self.aliases.items():
            artefact_dict[alias] = artefact_dict[target]
        return artefact_dict

    @override
    def get_typed_object_or_attribute(self, name: str, wanted_type: Optional[Type[Any]] = None) -> Any:
        # TODO: Add unit tests for this method
        if "." in name:
            parts = name.split(".", 1)  # Split only at the first dot
            base_name = parts[0]
            attr_path_str = parts[1]  # Keep the rest as a dot-separated string

            base_stuff = self.get_stuff(base_name)

            try:
                stuff_content = attrgetter(attr_path_str)(base_stuff.content)
            except AttributeError as exc:
                raise WorkingMemoryStuffAttributeNotFoundError(
                    variable_name=name,
                    message=f"Stuff attribute not found in attribute path '{name}': {exc}",
                ) from exc

            # Sometimes, some stuff content are Optional, therefore can be None. So Do not impose a wanted type
            if stuff_content is not None and wanted_type is not None and not isinstance(stuff_content, wanted_type):
                raise WorkingMemoryTypeError(
                    variable_name=name,
                    message=f"Content at '{name}' is of type {type(stuff_content).__name__}, it should be {wanted_type.__name__}",
                )

            return stuff_content
        else:
            content = self.get_stuff(name).content

            if wanted_type is not None and not isinstance(content, wanted_type):
                raise WorkingMemoryTypeError(
                    variable_name=name,
                    message=f"Content of '{name}' is of type {type(content).__name__}, it should be {wanted_type.__name__}",
                )

            return content

    ################################################################################################
    # Stuff accessors
    ################################################################################################

    def get_stuff_as(self, name: str, content_type: Type[StuffContentType]) -> StuffContentType:
        """Get stuff content as StuffContentType."""
        return self.get_stuff(name=name).content_as(content_type=content_type)

    def get_stuff_as_list(self, name: str, item_type: Type[StuffContentType]) -> ListContent[StuffContentType]:
        """
        Get stuff content as ListContent with items of type StuffContentType.
        If the items are of possibly various types, use item_type=StuffContent.
        """
        return self.get_stuff(name=name).as_list_of_fixed_content_type(item_type=item_type)

    def get_list_stuff_first_item_as(self, name: str, item_type: Type[StuffContentType]) -> StuffContentType:
        """Get stuff content as ListContent with items of type StuffContentType then return the first item."""
        return self.get_stuff_as_list(name=name, item_type=item_type).items[0]

    def get_stuff_as_text(self, name: str) -> TextContent:
        """Get stuff content as TextContent if applicable."""
        return self.get_stuff(name=name).as_text

    def get_stuff_as_str(self, name: str) -> str:
        """Get stuff content as string if applicable."""
        return self.get_stuff_as_text(name=name).text

    def get_stuff_as_image(self, name: str) -> ImageContent:
        """Get stuff content as ImageContent if applicable."""
        return self.get_stuff(name=name).as_image

    def get_stuff_as_text_and_image(self, name: str) -> TextAndImagesContent:
        """Get stuff content as TextAndImageContent if applicable."""
        return self.get_stuff(name=name).as_text_and_image

    def get_stuff_as_pdf(self, name: str) -> PDFContent:
        """Get stuff content as PDFContent if applicable."""
        return self.get_stuff(name=name).as_pdf

    def get_stuff_as_number(self, name: str) -> NumberContent:
        """Get stuff content as NumberContent if applicable."""
        return self.get_stuff(name=name).as_number

    def get_stuff_as_html(self, name: str) -> HtmlContent:
        """Get stuff content as HtmlContent if applicable."""
        return self.get_stuff(name=name).as_html

    def get_stuff_as_mermaid(self, name: str) -> MermaidContent:
        """Get stuff content as MermaidContent if applicable."""
        return self.get_stuff(name=name).as_mermaid

    ################################################################################################
    # Main stuff accessors
    ################################################################################################

    def main_stuff_as(self, content_type: Type[StuffContentType]) -> StuffContentType:
        """Get main stuff content as StuffContentType."""
        return self.get_stuff_as(name=MAIN_STUFF_NAME, content_type=content_type)

    def main_stuff_as_list(self, item_type: Type[StuffContentType]) -> ListContent[StuffContentType]:
        """
        Get main stuff content as ListContent with items of type StuffContentType.
        If the items are of possibly various types, use item_type=StuffContent.
        """
        return self.get_stuff_as_list(name=MAIN_STUFF_NAME, item_type=item_type)

    def main_list_stuff_first_item_as(self, item_type: Type[StuffContentType]) -> StuffContentType:
        """Get main stuff content as first list item of type StuffContentType."""
        return self.get_list_stuff_first_item_as(name=MAIN_STUFF_NAME, item_type=item_type)

    @property
    def main_stuff_as_text(self) -> TextContent:
        """Get main stuff content as TextContent if applicable."""
        return self.get_stuff_as_text(name=MAIN_STUFF_NAME)

    @property
    def main_stuff_as_image(self) -> ImageContent:
        """Get main stuff content as ImageContent if applicable."""
        return self.get_stuff_as_image(name=MAIN_STUFF_NAME)

    @property
    def main_stuff_as_text_and_image(self) -> TextAndImagesContent:
        """Get main stuff content as TextAndImageContent if applicable."""
        return self.get_stuff_as_text_and_image(name=MAIN_STUFF_NAME)

    @property
    def main_stuff_as_number(self) -> NumberContent:
        """Get main stuff content as NumberContent if applicable."""
        return self.get_stuff_as_number(name=MAIN_STUFF_NAME)

    @property
    def main_stuff_as_html(self) -> HtmlContent:
        """Get main stuff content as HtmlContent if applicable."""
        return self.get_stuff_as_html(name=MAIN_STUFF_NAME)

    @property
    def main_stuff_as_mermaid(self) -> MermaidContent:
        """Get main stuff content as MermaidContent if applicable."""
        return self.get_stuff_as_mermaid(name=MAIN_STUFF_NAME)
