from pathlib import Path

import shortuuid
from mthds.protocol.pipeline_inputs import PipelineInputs
from polyfactory.exceptions import FactoryException
from pydantic import BaseModel, ValidationError

from pipelex import log
from pipelex.cogt.content_generation.dry_mock import stamp_mock_main_coordination
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.memory.exceptions import WorkingMemoryFactoryError
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, StuffDict, WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs, NamedStuffSpec, TypedNamedStuffSpec
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.runtime_hub import get_class_registry

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
        *,
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
        *,
        concept_provider: ConceptProviderAbstract,
        input_specs: InputStuffSpecs | None = None,
        search_domain_codes: list[str] | None = None,
        inputs_base_dir: Path | None = None,
    ) -> WorkingMemory:
        """Create a WorkingMemory from a pipeline inputs dictionary.

        When ``input_specs`` is provided (the entry pipe's declared inputs), each value is
        interpreted **top-down against its declared concept** by the :class:`InputShaper` (Smart
        Inputs): a bare string becomes the declared concept, a bare number/dict/list is shaped to
        it, the ``{concept, content}`` envelope is compat-checked, and an undeclared name is a hard
        error (D8). When ``input_specs`` is ``None`` (no signature available), each value is shaped
        **bottom-up** from its own shape alone — today's behavior, unchanged.

        Args:
            pipeline_inputs: Dictionary in the format from API serialization
            concept_provider: Resolves concepts and answers compatibility questions. Injected rather
                than looked up so this module stays out of the method interpreter's import closure
                (see hub-layering); the caller holds the loaded method's library.
            input_specs: The entry pipe's declared inputs; ``None`` disables signature-driven shaping
            search_domain_codes: List of domain codes to search for concepts
            inputs_base_dir: Directory that bare *relative local* file paths resolve against (D3);
                the inputs file's parent when inputs were file-loaded by a CLI. ``None`` for API/SDK
                and in-process callers (they pass absolute urls / storage uris). Only consulted by
                the shaper's file-ish / CSV arms.

        Returns:
            WorkingMemory object reconstructed from the implicit format

        """
        if input_specs is not None:
            return InputShaper.shape(
                pipeline_inputs,
                concept_provider=concept_provider,
                input_specs=input_specs,
                search_domain_codes=search_domain_codes,
                inputs_base_dir=inputs_base_dir,
            )

        working_memory = cls.make_empty()

        for stuff_key, stuff_content_or_data in pipeline_inputs.items():
            stuff = StuffFactory.make_stuff_from_stuff_content_or_data(
                name=stuff_key,
                stuff_content_or_data=stuff_content_or_data,
                concept_provider=concept_provider,
                search_domain_codes=search_domain_codes,
            )
            working_memory.add_new_stuff(name=stuff_key, stuff=stuff)
        return working_memory

    @classmethod
    def convert_to_working_memory_format(cls, needed_inputs_spec: InputStuffSpecs) -> list[TypedNamedStuffSpec]:
        """Convert a pipe's needed inputs into the typed specs consumed by ``make_mock_inputs``.

        Args:
            needed_inputs_spec: The pipe's needed inputs (with detailed requirements).

        Returns:
            List of ``TypedNamedStuffSpec``, one per needed input, with the structure class
            resolved from the class registry (falling back to ``TextContent`` when missing).

        """
        needed_inputs_for_factory: list[TypedNamedStuffSpec] = []
        class_registry = get_class_registry()

        # TODO: fail and raise properly
        for named_stuff_spec in needed_inputs_spec.named_stuff_specs:
            try:
                # Get the concept and its structure class
                concept = named_stuff_spec.concept
                structure_class_name = concept.structure_class_name

                # Get the actual class from the registry
                structure_class = class_registry.get_class(name=structure_class_name)

                if structure_class and issubclass(structure_class, StuffContent):
                    typed_named_stuff_spec = TypedNamedStuffSpec.make_from_named(
                        named=named_stuff_spec,
                        structure_class=structure_class,
                    )
                    needed_inputs_for_factory.append(typed_named_stuff_spec)
                else:
                    # Fallback to TextContent if we can't get the proper class
                    log.verbose(
                        f"Could not get structure class '{structure_class_name}' for "
                        f"concept '{named_stuff_spec.concept.code}', falling back to TextContent",
                    )
                    text_typed_named_stuff_spec = TypedNamedStuffSpec.make_from_named(
                        named=named_stuff_spec,
                        structure_class=TextContent,
                    )
                    needed_inputs_for_factory.append(text_typed_named_stuff_spec)

            except ValidationError as exc:
                # Fallback to TextContent when the typed stuff spec fails pydantic validation
                log.warning(f"Error getting structure class for concept '{named_stuff_spec.concept.code}': {exc}, falling back to TextContent")
                text_typed_named_stuff_spec = TypedNamedStuffSpec.make_from_named(
                    named=named_stuff_spec,
                    structure_class=TextContent,
                )
                needed_inputs_for_factory.append(text_typed_named_stuff_spec)

        return needed_inputs_for_factory

    @classmethod
    def convert_stuff_spec_to_typed_named(cls, stuff_spec: StuffSpec, *, name: str) -> TypedNamedStuffSpec:
        """Resolve a single output `StuffSpec` to a `TypedNamedStuffSpec`.

        Mirrors the class-registry lookup behavior of ``convert_to_working_memory_format``:
        looks up the concept's `structure_class_name`, and falls back to `TextContent` when the
        class is missing from the registry (matching the existing fallback for inputs).
        """
        class_registry = get_class_registry()
        concept = stuff_spec.concept
        structure_class_name = concept.structure_class_name
        named = NamedStuffSpec(
            variable_name=name,
            concept=concept,
            multiplicity=stuff_spec.multiplicity,
        )
        structure_class = class_registry.get_class(name=structure_class_name)
        if structure_class and issubclass(structure_class, StuffContent):
            return TypedNamedStuffSpec.make_from_named(named=named, structure_class=structure_class)
        log.verbose(
            f"Could not get structure class '{structure_class_name}' for concept '{concept.code}', falling back to TextContent",
        )
        return TypedNamedStuffSpec.make_from_named(named=named, structure_class=TextContent)

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
    def make_mock_stuff(cls, typed_named_stuff_spec: TypedNamedStuffSpec) -> Stuff:
        """Create a single mock `Stuff` from a `TypedNamedStuffSpec`.

        Honors multiplicity: a non-multiple spec yields a `Stuff` of mock content;
        a multiple spec yields a `Stuff` whose content is a `ListContent` of mock items.
        Errors from `make_mock_content` are allowed to propagate — the legacy
        `make_mock_inputs` loop is the one place that swallows them with a fallback.
        """
        if not typed_named_stuff_spec.multiplicity:
            mock_content = cls.make_mock_content(typed_named_stuff_spec)
            return StuffFactory.make_stuff(
                concept=typed_named_stuff_spec.concept,
                content=mock_content,
                name=typed_named_stuff_spec.variable_name,
                code=shortuuid.uuid()[:5],
            )

        if isinstance(typed_named_stuff_spec.multiplicity, bool):
            nb_stuffs = 2
        else:
            nb_stuffs = typed_named_stuff_spec.multiplicity

        items: list[StuffContent] = [cls.make_mock_content(typed_named_stuff_spec) for _ in range(nb_stuffs)]
        stamp_mock_main_coordination(items)

        mock_list_content = ListContent[StuffContent](items=items)
        return StuffFactory.make_stuff(
            concept=typed_named_stuff_spec.concept,
            content=mock_list_content,
            name=typed_named_stuff_spec.variable_name,
            code=shortuuid.uuid()[:5],
        )

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
                mock_stuff = cls.make_mock_stuff(typed_named_stuff_spec)
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
