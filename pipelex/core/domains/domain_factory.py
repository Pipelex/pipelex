from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint


class DomainFactory:
    @classmethod
    def make_from_blueprint(cls, blueprint: DomainBlueprint) -> Domain:
        return Domain(
            code=blueprint.code,
            definition=blueprint.definition,
            system_prompt=blueprint.system_prompt,
            system_prompt_to_structure=blueprint.system_prompt_to_structure,
            prompt_template_to_structure=blueprint.prompt_template_to_structure,
        )
