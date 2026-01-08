import shortuuid
from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel

from pipelex import log
from pipelex.client.protocol import PipelineInputs
from pipelex.core.memory.exceptions import WorkingMemoryFactoryError
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, StuffDict, WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import TypedNamedStuffSpec
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent


class WorkingMemoryFactory(BaseModel):
    @classmethod
    def make_from_single_stuff(cls, stuff: Stuff) -> WorkingMemory:
        if not stuff.stuff_name:
            msg = f"Cannot make_from_single_stuff because stuff has no name: {stuff}"
            raise WorkingMemoryFactoryError(msg)
        stuff_dict: StuffDict = {stuff.stuff_name: stuff}
        return WorkingMemory(root=stuff_dict, aliases={MAIN_STUFF_NAME: stuff.stuff_name})

    @classmethod
    def make_from_multiple_stuffs(
        cls,
        stuff_list: list[Stuff],
        main_name: str | None = None,
        is_ignore_unnamed: bool = False,
    ) -> WorkingMemory:
        stuff_dict: StuffDict = {}
        for stuff in stuff_list:
            name = stuff.stuff_name
            if not name:
                if is_ignore_unnamed:
                    continue
                msg = f"Stuff {stuff} has no name"
                raise WorkingMemoryFactoryError(msg)
            stuff_dict[name] = stuff
        aliases: dict[str, str] = {}
        if stuff_dict:
            if main_name:
                aliases[MAIN_STUFF_NAME] = main_name
            else:
                aliases[MAIN_STUFF_NAME] = next(iter(stuff_dict.keys()))
        return WorkingMemory(root=stuff_dict, aliases=aliases)

    @classmethod
    def make_empty(cls) -> WorkingMemory:
        return WorkingMemory(root={})

    @classmethod
    def make_from_pipeline_inputs(
        cls,
        pipeline_inputs: PipelineInputs,
        search_domain_codes: list[str] | None = None,
    ) -> WorkingMemory:
        """Create a WorkingMemory from a pipeline inputs dictionary.

        Args:
            pipeline_inputs: Dictionary in the format from API serialization
            search_domain_codes: List of domain codes to search for concepts

        Returns:
            WorkingMemory object reconstructed from the implicit format

        """
        working_memory = cls.make_empty()

        for stuff_key, stuff_content_or_data in pipeline_inputs.items():
            stuff = StuffFactory.make_stuff_from_stuff_content_or_data(
                name=stuff_key,
                stuff_content_or_data=stuff_content_or_data,
                search_domain_codes=search_domain_codes,
            )
            working_memory.add_new_stuff(name=stuff_key, stuff=stuff)
        return working_memory

    @classmethod
    def create_mock_content(cls, typed_named_stuff_spec: TypedNamedStuffSpec) -> StuffContent:
        """Helper method to create mock content for a typed_named_stuff_spec."""

        class MockFactory(ModelFactory[typed_named_stuff_spec.structure_class]):  # type: ignore[name-defined]
            __model__ = typed_named_stuff_spec.structure_class
            __check_model__ = True
            __use_examples__ = True
            __allow_none_optionals__ = False  # Ensure Optional fields always get values

        return MockFactory.build(factory_use_construct=True)  # type: ignore[no-any-return]

    @classmethod
    def make_mock_inputs(cls, needed_inputs: list[TypedNamedStuffSpec]) -> "WorkingMemory":
        """Create a WorkingMemory with mock objects for the needed inputs.

        Args:
            needed_inputs: List of tuples (stuff_name, concept_code, structure_class)

        Returns:
            WorkingMemory with mock objects for each needed input

        """
        working_memory = cls.make_empty()

        for typed_named_stuff_spec in needed_inputs:
            try:
                if not typed_named_stuff_spec.multiplicity:
                    mock_content = cls.create_mock_content(typed_named_stuff_spec)

                    # Create stuff with mock content
                    mock_stuff = StuffFactory.make_stuff(
                        concept=typed_named_stuff_spec.concept,
                        content=mock_content,
                        name=typed_named_stuff_spec.variable_name,
                        code=shortuuid.uuid()[:5],
                    )

                    working_memory.add_new_stuff(name=typed_named_stuff_spec.variable_name, stuff=mock_stuff)
                else:
                    # Let's create a ListContent of multiple stuffs
                    nb_stuffs: int
                    if isinstance(typed_named_stuff_spec.multiplicity, bool):
                        # TODO: make this configurable or use existing config variable
                        nb_stuffs = 3
                    else:
                        nb_stuffs = typed_named_stuff_spec.multiplicity

                    items: list[StuffContent] = []
                    for _ in range(nb_stuffs):
                        item_mock_content = cls.create_mock_content(typed_named_stuff_spec)
                        items.append(item_mock_content)

                    mock_list_content = ListContent[StuffContent](items=items)

                    # Create stuff with mock content
                    mock_stuff = StuffFactory.make_stuff(
                        concept=typed_named_stuff_spec.concept,
                        content=mock_list_content,
                        name=typed_named_stuff_spec.variable_name,
                        code=shortuuid.uuid()[:5],
                    )

                    working_memory.add_new_stuff(name=typed_named_stuff_spec.variable_name, stuff=mock_stuff)

            except Exception as exc:
                log.warning(
                    f"Failed to create mock for '{typed_named_stuff_spec.variable_name}' ({typed_named_stuff_spec.concept.code}): "
                    f"{exc}. Using fallback text content."
                )
                # Create fallback text content
                fallback_content = TextContent(
                    text=f"DRY RUN: Fallback mock for '{typed_named_stuff_spec.variable_name}' ({typed_named_stuff_spec.concept.code})"
                )
                fallback_stuff = StuffFactory.make_stuff(
                    concept=typed_named_stuff_spec.concept,
                    content=fallback_content,
                    name=typed_named_stuff_spec.variable_name,
                    code=shortuuid.uuid()[:5],
                )
                working_memory.add_new_stuff(name=typed_named_stuff_spec.variable_name, stuff=fallback_stuff)
        return working_memory
