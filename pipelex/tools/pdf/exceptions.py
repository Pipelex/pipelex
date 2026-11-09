from typing import Any, Self

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.cogt.extract.extract_input import PAGE_VIEWS_FILE_ADVICE
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.system.exceptions import ToolError


class PdfDocumentUnreadableError(ToolError):
    """PDFium could not open a file it was asked to draw page views from.

    Page views are drawn from a PDF, so a file of any other format lands here, as does a damaged or password-protected
    PDF. It is what catches a file whose format nothing established, a URL that declares no type above all, which run
    setup never fetches and so cannot refuse. The message quotes PDFium's own reason, which names neither a URL nor the
    file's content. The renderer does not know the input; the leaf that does names it with :meth:`with_input`.
    """

    error_code = CoreCode.INPUT_FILE_UNREADABLE
    user_action = UserAction(kind=UserActionKind.CHANGE_INPUT, detail=PAGE_VIEWS_FILE_ADVICE)

    def __init__(self, message: str):
        super().__init__(message)
        # The input the file came from, as a caller writes it, which the catch site that knows it gives.
        self.input_name: str | None = None

    def with_input(self, *, input_name: str) -> Self:
        """Name, where it is caught, the input whose file could not be opened.

        Returns:
            This error, so that the catch site can re-raise it.
        """
        self.input_name = input_name
        return self

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"input": self.input_name, "file_type": "pdf", "reason": "pdf_load_failed"}
