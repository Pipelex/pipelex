from enum import StrEnum


class TemplateOwner(StrEnum):
    """Who wrote a template, which decides whose fault a failure of the template is.

    The render serves both: a method's templates (its prompts, expressions and compositions) and the templates Pipelex
    ships to display contents and graphs. A failure of a method's template is the method's, and its message may name
    what the template did; a failure of Pipelex's own is ours, and its message never reaches a caller.
    """

    METHOD = "method"
    PIPELEX = "pipelex"

    @property
    def is_method(self) -> bool:
        """Whether the template is the method's own, whose failure is the method's to fix."""
        match self:
            case TemplateOwner.METHOD:
                return True
            case TemplateOwner.PIPELEX:
                return False
