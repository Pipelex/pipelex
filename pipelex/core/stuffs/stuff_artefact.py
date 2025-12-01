from typing import Any

from jinja2.runtime import Context
from pydantic import RootModel
from typing_extensions import override

from pipelex.cogt.templating.templating_style import TextFormat
from pipelex.core.stuffs.exceptions import StuffArtefactError
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey, Jinja2TaggableAbstract
from pipelex.types import StrEnum


class BaseStuffArtefactField(StrEnum):
    STUFF_NAME = "_stuff_name"
    CONTENT_CLASS = "_content_class"
    CONCEPT_CODE = "_concept_code"
    STUFF_CODE = "_stuff_code"
    CONTENT = "_content"


class StuffArtefact(RootModel[dict[str, Any]], Jinja2TaggableAbstract):
    """A flattened representation of Stuff and its content as a dictionary.

    This RootModel implementation allows for subscript access to the underlying dictionary
    while maintaining type safety. It's particularly useful for injecting into jinja2 templates
    as a context variable.

    Note that in jinja2, subscripts to access the dict values are compatible with the dot notation
    e.g. {{ variable.field_name }} is equivalent to {{ variable['field_name'] }}
    """

    @override
    def __getattribute__(self, key: str) -> Any:
        """Prioritize dict keys over methods for attribute access in Jinja2 templates.

        This allows templates to use {{ stuff.items }} to access the 'items' key
        instead of getting the dict.items() method.
        """
        # Allow access to special attributes, 'root', and model-related attributes
        if key.startswith("_") or key in {"root", "model_dump", "model_config"}:
            return object.__getattribute__(self, key)

        # Check if it's a key in the root dict first
        try:
            root_dict = object.__getattribute__(self, "root")
            if key in root_dict:
                return root_dict[key]
        except AttributeError:
            pass

        # Fall back to normal attribute/method access
        return object.__getattribute__(self, key)

    def __getitem__(self, key: str) -> Any:
        return self.root[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.root[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.root.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.root

    def keys(self):
        return self.root.keys()

    def values(self):
        return self.root.values()

    def items(self):
        return self.root.items()

    def rendered_str(self, text_format: TextFormat) -> str:
        content = self.root[BaseStuffArtefactField.CONTENT]
        if not isinstance(content, StuffContent):
            msg = f"StuffArtefact has no StuffContent, content: {self}"
            raise StuffArtefactError(msg)
        return content.rendered_str(text_format=text_format)

    @override
    def render_tagged_for_jinja2(self, context: Context, tag_name: str | None = None) -> tuple[Any, str | None]:
        # TODO: factorize the text formatting with the jinja2 "text_format" filter
        text_format = context.get(Jinja2ContextKey.TEXT_FORMAT, default=TextFormat.PLAIN)
        rendered_str = self.rendered_str(text_format=text_format)

        tag_name = tag_name or self.get(BaseStuffArtefactField.STUFF_NAME)

        return rendered_str, tag_name
