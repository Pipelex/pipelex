"""Factory for creating pipes from various sources."""

from typing import Any, Dict, Type

from kajson.exceptions import ClassRegistryInheritanceError, ClassRegistryNotFoundError
from kajson.kajson_manager import KajsonManager

from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_blueprint import PipeSpecificFactoryProtocol
from pipelex.exceptions import PipeFactoryError


class PipeFactory:
    """Factory class for creating pipes from different representations."""

    @staticmethod
    def make_pipe_from_details_dict(
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeAbstract:
        """Create a pipe from a details dictionary.

        The first line in the details_dict should be the pipe definition in the format:
        PipeClassName = "the pipe's definition in natural language"

        Args:
            domain_code: The domain code for the pipe
            pipe_code: The unique code for the pipe
            details_dict: Dictionary containing pipe configuration

        Returns:
            PipeAbstract: The created pipe instance

        Raises:
            PipeFactoryError: If the pipe cannot be created
        """
        # First line in the details_dict is the pipe definition
        pipe_definition: str
        pipe_class_name: str
        try:
            pipe_class_name, pipe_definition = next(iter(details_dict.items()))
            details_dict.pop(pipe_class_name)
        except StopIteration as details_dict_empty_error:
            raise PipeFactoryError(f"Pipe '{pipe_code}' could not be created because its blueprint is empty.") from details_dict_empty_error

        # The factory class name for that specific type of Pipe is the pipe class name with "Factory" suffix
        factory_class_name = f"{pipe_class_name}Factory"
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

        details_dict["definition"] = pipe_definition
        details_dict["domain"] = domain_code
        pipe_from_blueprint: PipeAbstract = pipe_factory.make_pipe_from_details_dict(
            domain_code=domain_code,
            pipe_code=pipe_code,
            details_dict=details_dict,
        )
        return pipe_from_blueprint
