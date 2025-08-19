from typing import Any, Type

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from kajson.kajson_manager import KajsonManager

from pipelex.core.pipe.pipe_abstract import PipeAbstract
from pipelex.core.pipe.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.exceptions import PipeFactoryError


class PipeFactory:
    @classmethod
    def make_pipe_from_blueprint(
        cls,
        pipe_code: str,
        pipe_blueprint: PipeBlueprint,
        domain: str,
    ) -> PipeAbstract:
        # The factory class name for that specific type of Pipe is the pipe class name with "Factory" suffix
        factory_class_name = f"{pipe_blueprint.type}Factory"
        try:
            pipe_factory: Type[PipeSpecificFactoryProtocol[Any, Any]] = KajsonManager.get_class_registry().get_required_subclass(
                name=factory_class_name,
                base_class=PipeSpecificFactoryProtocol,
            )
        except ClassRegistryNotFoundError as factory_not_found_error:
            raise PipeFactoryError(
                f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' not found: {factory_not_found_error}"
            ) from factory_not_found_error
        except ClassRegistryInheritanceError as factory_inheritance_error:
            raise PipeFactoryError(
                f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' is not a subclass of {type(PipeSpecificFactoryProtocol)}."
            ) from factory_inheritance_error

        pipe_from_blueprint: PipeAbstract = pipe_factory.make_pipe_from_blueprint(
            domain_code=domain,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
        return pipe_from_blueprint
