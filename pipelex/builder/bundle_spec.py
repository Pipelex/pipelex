from typing import TYPE_CHECKING, Any, cast

from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.exceptions import PipelexBundleSpecBlueprintError
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.core.domains.exceptions import DomainCodeError
from pipelex.core.domains.validation import validate_domain_code
from pipelex.core.pipes.pipe_blueprint import SIGNATURE_ONLY_KEYS, normalize_typeless_signature_section
from pipelex.core.pipes.validation import is_pipe_code_valid
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.mthds_parsing.pipe_sorter import sort_pipes_by_dependencies
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.core.concepts.concept_blueprint import ConceptBlueprint

# The spec layer's typeless-signature allowlist is the shared blueprint contract set adapted to the
# spec's actual field surface: drop `source` (a blueprint-only field — `PipeSpec` has no `source` and
# forbids extras, so a typeless section carrying it must hit the teaching error, not be injected and
# then rejected with a raw pydantic message) and add the structural `pipe_code` field (the blueprint
# uses the dict key; the spec section carries it explicitly). Any other key on a typeless section
# still triggers the teaching error.
SIGNATURE_ONLY_SPEC_KEYS: frozenset[str] = (SIGNATURE_ONLY_KEYS - {"source"}) | {"pipe_code"}


class PipelexBundleSpec(StructuredContent):
    """Complete spec of a Pipelex bundle TOML definition.

    Represents the top-level structure of a Pipelex bundle, which defines a domain
    with its concepts, pipes, and configuration. Bundles are the primary unit of
    organization for Pipelex methods, loaded from TOML files.

    Attributes:
        domain: The domain identifier for this bundle in snake_case format.
               Serves as the namespace for all concepts and pipes within.
        description: Natural language description of the pipeline's purpose and functionality.
        system_prompt: Default system prompt applied to all LLM pipes in the bundle
                      unless overridden at the pipe level.
        main_pipe: The main pipe of the bundle.
        concept: Dictionary of concept definitions used in this domain. Keys are concept
                codes in PascalCase format, values are ConceptSpec instances or plain
                strings used as the concept's description.
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
    def validate_domain_syntax(cls, domain_code: str) -> str:
        try:
            validate_domain_code(code=domain_code)
        except DomainCodeError as exc:
            msg = f"Error when trying to validate pipelex bundle spec: domain '{domain_code}' is not a valid domain code: {exc}"
            raise ValueError(msg) from exc
        return domain_code

    @field_validator("pipe", mode="before")
    @classmethod
    def validate_pipe_keys(cls, pipe: Any) -> Any:
        """Validate pipe codes and normalize typeless sections before the discriminated union runs.

        Full mirror of `PipelexBundleBlueprint.validate_pipe_keys`: each dict key (the pipe code) is
        rejected up front if not snake_case, then each section is normalized. A spec `[pipe.x]`
        section with no `type` whose keys are exactly the signature contract
        (`SIGNATURE_ONLY_SPEC_KEYS`) has the internal `PipeSignature` discriminator injected, so the
        union routes it to `PipeSignatureSpec` — the author never writes the tag. A typeless section
        that declares anything more is describing an implementation without naming its type, which is
        a hard error. A section that already names a `type` (or is an already-built spec instance
        rather than a raw dict) passes through untouched.
        """
        if pipe is None:
            return None
        if not isinstance(pipe, dict):
            # Let the field type raise its own "should be a dict" error.
            return pipe
        typed_pipe = cast("dict[Any, Any]", pipe)
        normalized: dict[Any, Any] = {}
        for pipe_code, pipe_section in typed_pipe.items():
            if isinstance(pipe_code, str) and not is_pipe_code_valid(pipe_code=pipe_code):
                msg = f"Pipe code '{pipe_code}' is not a valid pipe code. Must be in snake_case."
                raise ValueError(msg)
            normalized[pipe_code] = normalize_typeless_signature_section(
                pipe_code=pipe_code, pipe_section=pipe_section, allowed_keys=SIGNATURE_ONLY_SPEC_KEYS
            )
        return normalized

    @model_validator(mode="after")
    def validate_main_pipe(self) -> "PipelexBundleSpec":
        if not self.pipe or (self.main_pipe not in self.pipe):
            msg = f"Main pipe '{self.main_pipe}' could not be found in bundle spec"
            raise ValueError(msg)
        return self

    def to_blueprint(self) -> PipelexBundleBlueprint:
        concept: dict[str, ConceptBlueprint | str] | None = None

        if self.concept:
            concept = {}
            for concept_code, concept_spec_or_name in self.concept.items():
                if isinstance(concept_spec_or_name, ConceptSpec):
                    concept[concept_code] = concept_spec_or_name.to_blueprint()
                else:
                    # A bare string is a concept description — the blueprint layer accepts it as-is
                    concept[concept_code] = concept_spec_or_name

        pipe: dict[str, PipeBlueprintUnion] | None = None
        if self.pipe:
            # First, convert all specs to blueprints
            pipe_blueprints: dict[str, PipeBlueprintUnion] = {}
            for pipe_code, pipe_spec in self.pipe.items():
                try:
                    pipe_blueprints[pipe_code] = pipe_spec.to_blueprint()
                except ValidationError as exc:
                    msg = f"Failed to create pipe blueprint from spec for pipe code {pipe_code}: {format_pydantic_validation_error(exc)}"
                    raise PipelexBundleSpecBlueprintError(msg) from exc

            # Then, sort blueprints by dependencies
            sorted_pipe_items = sort_pipes_by_dependencies(pipe_blueprints, domain_code=self.domain)
            # Finally, create the ordered dict
            pipe = dict[str, PipeBlueprintUnion](sorted_pipe_items)

        try:
            return PipelexBundleBlueprint(
                domain=self.domain,
                description=self.description,
                system_prompt=self.system_prompt,
                main_pipe=self.main_pipe,
                pipe=pipe,
                concept=concept,
            )
        except ValidationError as exc:
            msg = f"Failed to create pipelex bundle blueprint: {format_pydantic_validation_error(exc)}"
            raise PipelexBundleSpecBlueprintError(msg) from exc

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        bundle_group = Group()

        # Bundle header info
        if title:
            bundle_group.renderables.append(Text(title, style="bold"))
        bundle_group.renderables.append(Text.from_markup(f"Domain: [yellow]{self.domain}[/yellow]\n", style="bold"))
        if self.description:
            bundle_group.renderables.append(Text.from_markup(f"Description: [yellow italic]{self.description}[/yellow italic]\n"))
        bundle_group.renderables.append(Text.from_markup(f"Main Pipe: [red]{self.main_pipe}[/red]\n"))
        if self.system_prompt:
            bundle_group.renderables.append(Text(f"System Prompt: {self.system_prompt}\n", style="dim"))

        # Concepts table
        if self.concept:
            bundle_group.renderables.append(Text("\n"))
            concepts_table = Table(
                title="Concepts", title_style="bold green", show_header=False, show_edge=True, show_lines=True, border_style="green"
            )
            concepts_table.add_column("Concept", style="white")

            for concept_code, concept_spec_or_name in self.concept.items():
                if isinstance(concept_spec_or_name, ConceptSpec):
                    concept_rendered = concept_spec_or_name.rendered_pretty()
                    concepts_table.add_row(concept_rendered)
                else:
                    # Plain string concept value: the string is the concept's description
                    concepts_table.add_row(Text.from_markup(f"[green]{concept_code}[/green]: {concept_spec_or_name}"))

            bundle_group.renderables.append(concepts_table)

        # Pipes table
        if self.pipe:
            bundle_group.renderables.append(Text("\n"))
            pipes_table = Table(title="Pipes", title_style="bold red", show_header=False, show_edge=True, show_lines=True, border_style="red")
            pipes_table.add_column("Pipe", style="white")

            for pipe_spec in self.pipe.values():
                pipe_rendered = pipe_spec.rendered_pretty()
                pipes_table.add_row(pipe_rendered)

            bundle_group.renderables.append(pipes_table)

        return bundle_group
