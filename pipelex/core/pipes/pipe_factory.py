from typing import Any, Protocol, Type, TypeVar

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from kajson.kajson_manager import KajsonManager
from typing_extensions import override, runtime_checkable

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeFactoryError

PipeBlueprintType = TypeVar("PipeBlueprintType", bound="PipeBlueprint", contravariant=True)
PipeType = TypeVar("PipeType", bound="PipeAbstract", covariant=True)


@runtime_checkable
class PipeFactoryProtocol(Protocol[PipeBlueprintType, PipeType]):
    @classmethod
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeBlueprintType,
    ) -> PipeType: ...


class PipeFactory(PipeFactoryProtocol[PipeBlueprint, PipeAbstract]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeBlueprint,
    ) -> PipeAbstract:
        # The factory class name for that specific type of Pipe is the pipe class name with "Factory" suffix
        factory_class_name = f"{pipe_blueprint.type}Factory"
        try:
            pipe_factory: Type[PipeFactoryProtocol[Any, Any]] = KajsonManager.get_class_registry().get_required_subclass(
                name=factory_class_name,
                base_class=PipeFactoryProtocol,
            )
        except ClassRegistryNotFoundError as factory_not_found_error:
            raise PipeFactoryError(
                f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' not found: {factory_not_found_error}"
            ) from factory_not_found_error
        except ClassRegistryInheritanceError as factory_inheritance_error:
            raise PipeFactoryError(
                f"Pipe '{pipe_code}' couldn't be created: factory '{factory_class_name}' is not a subclass of {type(PipeFactoryProtocol)}."
            ) from factory_inheritance_error

        pipe_from_blueprint: PipeAbstract = pipe_factory.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
        return pipe_from_blueprint
