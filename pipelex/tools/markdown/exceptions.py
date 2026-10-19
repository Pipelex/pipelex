from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import ToolError


class MarkdownParserDependencyError(ToolError):
    """Raised when markdown-it-py is installed without linkify-it-py, which Pipelex requires to read Markdown.

    The environment was installed without a dependency Pipelex declares, so whoever installed it fixes it.
    """

    error_code = PipelexErrorCode.CONFIG_DEPENDENCY_MISSING
