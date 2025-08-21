from typing import Dict

from pydantic import BaseModel

from pipelex.core.bundles.pipelex_bundle import PipelexBundle
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.domains.domain import Domain
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory


class PipelexBundleFactory(BaseModel):
    @classmethod
    def make_from_blueprint(cls, blueprint: PipelexBundleBlueprint) -> PipelexBundle:
        """Make a PipelexBundle from a PipelexBundleBlueprint."""
        domain = Domain(
            code=blueprint.domain,
            definition=blueprint.definition,
            system_prompt=blueprint.system_prompt,
            system_prompt_to_structure=blueprint.system_prompt_to_structure,
            prompt_template_to_structure=blueprint.prompt_template_to_structure,
        )
        concepts: Dict[str, Concept] = {}
        if blueprint.concept is not None:
            for concept_name, concept_blueprint_or_str in blueprint.concept.items():
                if isinstance(concept_blueprint_or_str, ConceptBlueprint):
                    concepts[concept_name] = ConceptFactory.make_concept_from_blueprint(
                        domain=blueprint.domain, code=concept_name, concept_blueprint=concept_blueprint_or_str
                    )
                else:
                    # One line concepts
                    concepts[concept_name] = ConceptFactory.make_concept_from_definition_str(
                        domain_code=blueprint.domain, concept_str=concept_name, definition=concept_blueprint_or_str
                    )

        pipes: Dict[str, PipeAbstract] = {}
        if blueprint.pipe is not None:
            for pipe_name, pipe_blueprint in blueprint.pipe.items():
                pipes[pipe_name] = PipeFactory.make_pipe_from_blueprint(
                    domain_code=blueprint.domain,
                    pipe_code=pipe_name,
                    pipe_blueprint=pipe_blueprint,
                )
        return PipelexBundle(domain=domain, concepts=concepts, pipes=pipes)
