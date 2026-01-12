from pipelex.types import StrEnum


class TextFormat(StrEnum):
    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"

    @property
    def render_method_name(self):
        return f"rendered_{self}"
