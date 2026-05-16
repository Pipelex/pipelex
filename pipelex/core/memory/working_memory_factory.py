import shortuuid
from mthds.models.pipeline_inputs import PipelineInputs
from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError

from pipelex import log
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.core.memory.exceptions import WorkingMemoryFactoryError
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, StuffDict, WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import TypedNamedStuffSpec
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent

# Field names that require snake_case format for pipelex bundle specs
# Note: main_pipe is NOT included here because BundleHeaderSpec.main_pipe has
# examples=["mock_main"] that should take precedence to coordinate with pipe_specs mocking
SNAKE_CASE_FIELD_NAMES = {"domain", "domain_code", "pipe_code"}

# Field names that require PascalCase format for pipelex concept specs
PASCAL_CASE_FIELD_NAMES = {"concept_code"}


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
    def make_mock_content(cls, typed_named_stuff_spec: TypedNamedStuffSpec) -> StuffContent:
        """Helper method to create mock content for a typed_named_stuff_spec.

        Uses DryRunFactory to generate mock values with field-specific generators
        for known constrained fields (e.g., domain, pipe_code require snake_case).

        For base classes that have concrete subclasses (like PipeSpec), picks a random
        subclass for mocking to ensure discriminator fields are valid.
        """
        structure_class = typed_named_stuff_spec.structure_class

        # Check if this is a base class with subclasses and pick a concrete one for mocking
        structure_class = cls._get_mockable_class(structure_class)

        mock_factory = DryRunFactory.make_dry_run_factory(
            object_class=structure_class,
            snake_case_field_names=SNAKE_CASE_FIELD_NAMES,
            pascal_case_field_names=PASCAL_CASE_FIELD_NAMES,
        )
        return mock_factory.build(factory_use_construct=True)  # type: ignore[no-any-return]

    @classmethod
    def _get_mockable_class(cls, structure_class: type[StuffContent]) -> type[StuffContent]:
        """Get a concrete class to use for mocking.

        If the class has subclasses defined in the same module (indicating it's a base class
        for a discriminated union), picks a random subclass. Otherwise returns the class as-is.
        """
        # Import here to avoid circular imports
        from pipelex.builder.pipe.pipe_spec import PipeSpec  # noqa: PLC0415

        # Check for specific base classes that need special handling
        if structure_class is PipeSpec:
            # PipeSpec has many subclasses - pick one that has minimal extra required fields
            # PipeBatchSpec is chosen as it's commonly used and has straightforward fields
            from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec  # noqa: PLC0415

            return PipeBatchSpec

        return structure_class

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
                    mock_content = cls.make_mock_content(typed_named_stuff_spec)

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
                    # For pipe_specs lists, ensure the first item uses "mock_main" as pipe_code
                    # to match the mock main_pipe in BundleHeaderSpec
                    nb_stuffs: int
                    if isinstance(typed_named_stuff_spec.multiplicity, bool):
                        # TODO: make this configurable or use existing config variable
                        nb_stuffs = 3
                    else:
                        nb_stuffs = typed_named_stuff_spec.multiplicity

                    items: list[StuffContent] = []
                    for idx in range(nb_stuffs):
                        item_mock_content = cls.make_mock_content(typed_named_stuff_spec)
                        # For the first item in pipe specs, set pipe_code to "mock_main"
                        # to match the mock main_pipe in BundleHeaderSpec
                        if idx == 0 and hasattr(item_mock_content, "pipe_code"):
                            item_mock_content.pipe_code = "mock_main"  # pyright: ignore[reportAttributeAccessIssue]
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

            except (FactoryException, ValidationError) as exc:
                # Mock build (polyfactory) or content validation (pydantic) failed for this dynamic
                # class — fall back to text content. Unexpected errors propagate.
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
