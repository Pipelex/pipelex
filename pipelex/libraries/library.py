from pydantic import BaseModel, Field

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.domains.domain_library import DomainLibrary
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.pipes.pipe_library import PipeLibrary


class Library(BaseModel):
    """A Library bundles together domain, concept, and pipe libraries for a specific context.
    
    This represents a complete set of Pipelex definitions (domains, concepts, pipes)
    that can be loaded and used together, typically for a single pipeline run.
    
    Each Library (except BASE) inherits native concepts and base pipes from the BASE library.
    """

    domain_library: DomainLibrary = Field(default_factory=DomainLibrary.make_empty)
    concept_library: ConceptLibrary = Field(default_factory=ConceptLibrary.make_empty)
    pipe_library: PipeLibrary = Field(default_factory=PipeLibrary.make_empty)

    @classmethod
    def make_empty(cls) -> "Library":
        """Create an empty library with initialized concept library (includes native concepts).
        
        This should only be used for the BASE library.
        """
        return cls(
            domain_library=DomainLibrary.make_empty(),
            concept_library=ConceptLibrary.make_empty(),
            pipe_library=PipeLibrary.make_empty(),
        )

    @classmethod
    def make_base(cls) -> "Library":
        """Create the BASE library that contains native concepts and builder pipes."""
        # 1 - Concept library, add the native concepts
        concept_library = ConceptLibrary.make_empty()
        all_native_concepts = ConceptFactory.make_all_native_concepts()
        concept_library.add_concepts(concepts=all_native_concepts)

        # 2 - Pipe library, add the builder pipes
        pipe_library = PipeLibrary.make_empty()
        
        # 3 - Domain library, add the domains
        domain_library = DomainLibrary.make_empty()
        
        return cls(
            domain_library=domain_library,
            concept_library=concept_library,
            pipe_library=pipe_library,
        )

    def teardown(self) -> None:
        """Teardown all libraries in this bundle."""
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    def validate_with_libraries(self) -> None:
        """Validate all libraries in this bundle."""
        self.concept_library.validate_with_libraries()
        self.pipe_library.validate_with_libraries()
        self.domain_library.validate_with_libraries()

    def load_from_blueprints(self, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        """Load domains, concepts, and pipes from a list of blueprints.
        
        Args:
            blueprints: List of parsed PLX blueprints to load
            
        Returns:
            List of all pipes that were loaded
        """
        all_pipes: list[PipeAbstract] = []
        
        # Load all domains first
        all_domains: list[Domain] = []
        for blueprint in blueprints:
            domain = self._load_domain_from_blueprint(blueprint)
            all_domains.append(domain)
        self.domain_library.add_domains(domains=all_domains)
        
        # Load all concepts second
        all_concepts: list[Concept] = []
        for blueprint in blueprints:
            concepts = self._load_concepts_from_blueprint(blueprint)
            all_concepts.extend(concepts)
        self.concept_library.add_concepts(concepts=all_concepts)
        
        # Load all pipes third
        for blueprint in blueprints:
            pipes = self._load_pipes_from_blueprint(blueprint)
            all_pipes.extend(pipes)
        self.pipe_library.add_pipes(pipes=all_pipes)
        
        return all_pipes

    def _load_domain_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> Domain:
        """Load a domain from a blueprint."""
        return DomainFactory.make_from_blueprint(
            blueprint=DomainBlueprint(
                source=blueprint.source,
                code=blueprint.domain,
                description=blueprint.description or "",
                system_prompt=blueprint.system_prompt,
                system_prompt_to_structure=blueprint.system_prompt_to_structure,
                prompt_template_to_structure=blueprint.prompt_template_to_structure,
            ),
        )

    def _load_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[Concept]:
        """Load concepts from a blueprint."""
        if blueprint.concept is None:
            return []

        concepts: list[Concept] = []
        for concept_code, concept_blueprint_or_description in blueprint.concept.items():
            concept = ConceptFactory.make_from_blueprint_or_description(
                domain=blueprint.domain,
                concept_code=concept_code,
                concept_codes_from_the_same_domain=list(blueprint.concept.keys()),
                concept_blueprint_or_description=concept_blueprint_or_description,
            )
            concepts.append(concept)
        return concepts

    def _load_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[PipeAbstract]:
        """Load pipes from a blueprint."""
        pipes: list[PipeAbstract] = []
        if blueprint.pipe is not None:
            for pipe_name, pipe_blueprint in blueprint.pipe.items():
                pipe = PipeFactory.make_from_blueprint(
                    domain=blueprint.domain,
                    pipe_code=pipe_name,
                    blueprint=pipe_blueprint,
                    concept_codes_from_the_same_domain=list(blueprint.concept.keys()) if blueprint.concept else None,
                )
                pipes.append(pipe)
        return pipes

