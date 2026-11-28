from typing import Any

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.system.exceptions import ToolError


class DataUrlError(ToolError):
    """Raised when a value read as a `data:` URL is not one this runtime reads.

    A value that is not a `data:` URL at all, a `data:` URL with no comma ending its header, and, where a reader needs
    bytes, a `data:` URL that is not base64. The message never quotes the header or the payload, which are a caller's
    content. The input boundary turns it into the caller's error, naming the input and the field; a reader that meets
    one in content a step produced reports it as ``input.file_unreadable`` all the same, since the file cannot be read.
    """

    error_code = CoreCode.INPUT_FILE_UNREADABLE

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"reason": "it is not a base64 data URL", "input": None, "file_type": None}
