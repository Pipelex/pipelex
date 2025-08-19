from typing import Dict

from pydantic import BaseModel

from pipelex.core.bundle.pipelex_bundle import PipelexBundle
from pipelex.core.bundle.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concept.concept import Concept
from pipelex.core.concept.concept_factory import ConceptFactory
from pipelex.core.domain.domain import Domain
from pipelex.core.pipe.pipe_abstract import PipeAbstract
from pipelex.core.pipe.pipe_factory import PipeFactory


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
        if blueprint.concepts is not None:
            for concept_name, concept_blueprint in blueprint.concepts.items():
                concepts[concept_name] = ConceptFactory.make_concept_from_blueprint(
                    domain=blueprint.domain, code=concept_name, concept_blueprint=concept_blueprint
                )
        pipes: Dict[str, PipeAbstract] = {}
        if blueprint.pipes is not None:
            for pipe_name, pipe_blueprint in blueprint.pipes.items():
                pipes[pipe_name] = PipeFactory.make_pipe_from_blueprint(
                    domain_code=blueprint.domain,
                    pipe_code=pipe_name,
                    pipe_blueprint=pipe_blueprint,
                )
        return PipelexBundle(domain=domain, concepts=concepts, pipes=pipes)
