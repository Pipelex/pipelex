from pydantic import ValidationError

from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.exceptions import DomainFactoryError
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class DomainFactory:
    @classmethod
    def make_from_blueprint(cls, blueprint: DomainBlueprint) -> Domain:
        try:
            return Domain(
                code=blueprint.code,
                description=blueprint.description,
                system_prompt=blueprint.system_prompt,
            )
        except ValidationError as exc:
            msg = f"Could not make domain from blueprint: {format_pydantic_validation_error(exc)}"
            raise DomainFactoryError(msg) from exc
