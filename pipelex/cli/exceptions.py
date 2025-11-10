from click import ClickException

from pipelex.core.concepts.exceptions import ConceptDefinitionErrorData
from pipelex.exceptions import PipelexException


class PipelexCLIError(PipelexException, ClickException):
    """Raised when there's an error in CLI usage or operation."""

class PipelexValidationExceptionAbstract(PipelexException):
    @abstractmethod
    def get_concept_definition_errors(self) -> list[ConceptDefinitionErrorData]:
        pass