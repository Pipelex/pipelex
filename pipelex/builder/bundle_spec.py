from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from pipelex.builder.builder_errors import (
    ConceptFailure,
    ConceptSpecError,
    PipeBuilderError,
    PipeFailure,
    PipelexBundleError,
    PipeSpecError,
)
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.core.bundles.pipe_sorter import sort_pipes_by_dependencies
from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class PipelexBundleSpec(StructuredContent):
    """Complete spec of a Pipelex bundle TOML definition.

    Represents the top-level structure of a Pipelex bundle, which defines a domain
    with its concepts, pipes, and configuration. Bundles are the primary unit of
    organization for Pipelex workflows, loaded from TOML files.

    Attributes:
        domain: The domain identifier for this bundle in snake_case format.
               Serves as the namespace for all concepts and pipes within.
        description: Natural language description of the pipeline's purpose and functionality.
        system_prompt: Default system prompt applied to all LLM pipes in the bundle
                      unless overridden at the pipe level.
        main_pipe: The main pipe of the bundle.
        concept: Dictionary of concept definitions used in this domain. Keys are concept
                codes in PascalCase format, values are ConceptBlueprint instances or
                string references to existing concepts.
        pipe: Dictionary of pipe definitions for data transformation. Keys are pipe
             codes in snake_case format, values are specific pipe spec types
             (PipeLLM, PipeImgGen, PipeSequence, etc.).

    Validation Rules:
        1. Domain must be in valid snake_case format.
        2. Concept keys must be in PascalCase format.
        3. Pipe keys must be in snake_case format.
        4. Extra fields are forbidden (strict mode).
        5. Pipe types must match their blueprint discriminator.

    """

    model_config = ConfigDict(extra="forbid")

    domain: str
    description: str | None = None
    system_prompt: str | None = None
    main_pipe: str

    concept: dict[str, ConceptSpec | str] | None = Field(default_factory=dict)

    pipe: dict[str, PipeSpecUnion] | None = Field(default_factory=dict)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain_syntax(cls, domain: str) -> str:
        DomainBlueprint.validate_domain_code(code=domain)
        return domain

    @model_validator(mode="after")
    def validate_main_pipe(self) -> "PipelexBundleSpec":
        if not self.pipe or (self.main_pipe not in self.pipe):
            msg = f"Main pipe '{self.main_pipe}' could not be found in bundle spec"
            raise PipelexBundleError(message=msg)
        return self

    def to_blueprint(self) -> PipelexBundleBlueprint:
        concept: dict[str, ConceptBlueprint | str] | None = None

        if self.concept:
            concept = {}
            for concept_code, concept_spec_or_name in self.concept.items():
                if isinstance(concept_spec_or_name, ConceptSpec):
                    try:
                        concept[concept_code] = concept_spec_or_name.to_blueprint()
                    except ValidationError as exc:
                        msg = f"Failed to create concept blueprint from spec for concept code {concept_code}: {format_pydantic_validation_error(exc)}"
                        concept_failure = ConceptFailure(concept_spec=concept_spec_or_name, error_message=msg)
                        raise ConceptSpecError(message=msg, concept_failure=concept_failure) from exc
                else:
                    concept[concept_code] = ConceptBlueprint(description=concept_code, structure=concept_spec_or_name)

        pipe: dict[str, PipeBlueprintUnion] | None = None
        if self.pipe:
            # First, convert all specs to blueprints
            pipe_blueprints: dict[str, PipeBlueprintUnion] = {}
            for pipe_code, pipe_spec in self.pipe.items():
                try:
                    pipe_blueprints[pipe_code] = pipe_spec.to_blueprint()
                except ValidationError as exc:
                    msg = f"Failed to create pipe blueprint from spec for pipe code {pipe_code}: {format_pydantic_validation_error(exc)}"
                    pipe_failure = PipeFailure(pipe_spec=pipe_spec, error_message=msg)
                    raise PipeSpecError(message=msg, pipe_failure=pipe_failure) from exc

            # Then, sort blueprints by dependencies
            try:
                sorted_pipe_items = sort_pipes_by_dependencies(pipe_blueprints)
            except Exception as exc:
                msg = f"Failed to sort pipes by dependencies: {exc}"
                raise PipeBuilderError(msg) from exc

            # Finally, create the ordered dict
            pipe = dict(sorted_pipe_items)

        return PipelexBundleBlueprint(
            domain=self.domain,
            description=self.description,
            system_prompt=self.system_prompt,
            main_pipe=self.main_pipe,
            pipe=pipe,
            concept=concept,
        )
