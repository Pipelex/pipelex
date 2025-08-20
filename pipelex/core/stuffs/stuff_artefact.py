from typing import Any, Dict, Optional, Tuple

from jinja2.runtime import Context
from pydantic import RootModel
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.exceptions import StuffArtefactError
from pipelex.tools.templating.jinja2_models import Jinja2ContextKey, Jinja2TaggableAbstract
from pipelex.tools.templating.templating_models import TextFormat


class StuffArtefact(RootModel[Dict[str, Any]], Jinja2TaggableAbstract):
    """A flattened representation of Stuff and its content as a dictionary.

    This RootModel implementation allows for subscript access to the underlying dictionary
    while maintaining type safety. It's particularly useful for injecting into jinja2 templates
    as a context variable.

    Note that in jinja2, subscripts to access the dict values are compatible with the dot notation
    e.g. {{ variable.field_name }} is equivalent to {{ variable['field_name'] }}
    """

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
        content = self.root["content"]
        if not isinstance(content, StuffContent):
            raise StuffArtefactError(f"StuffArtefact has no StuffContent, content: {self}")
        rendered_str = content.rendered_str(text_format=text_format)
        return rendered_str

    @override
    def render_tagged_for_jinja2(self, context: Context, tag_name: Optional[str] = None) -> Tuple[Any, Optional[str]]:
        # TODO: factorize the text formatting with the jinja2 "text_format" filter
        text_format = context.get(Jinja2ContextKey.TEXT_FORMAT, default=TextFormat.PLAIN)
        rendered_str = self.rendered_str(text_format=text_format)

        tag_name = tag_name or self.get("stuff_name")

        return rendered_str, tag_name
