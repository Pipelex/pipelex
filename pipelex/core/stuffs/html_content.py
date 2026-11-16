from typing import TYPE_CHECKING, ClassVar, cast

from kajson import kajson
from pydantic import Field
from typing_extensions import override

from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.tools.jinja2.jinja2_rendering import render_jinja2_sync
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.pretty import require_rich_for_rendering

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable


class HtmlContent(StoredValueContent):
    """HTML content"""

    value_field_name: ClassVar[str] = "inner_html"
    # `css_class` stays inline in both forms, beside the markup.
    value_form_field_names: ClassVar[tuple[str, ...]] = ("inner_html", "css_class")
    value_kind_desc: ClassVar[str] = "html"
    stored_mime_type: ClassVar[str] = "text/html"
    stored_file_extension: ClassVar[str] = "html"

    inner_html: str | None = Field(default=None, description="The inner HTML of the content")
    css_class: str | None = Field(default=None, description="The CSS class of the content")
    url: str | None = Field(default=None, description="The URL of the stored inner HTML: a storage URI, an HTTP(S) URL, or a base64 data URL")
    size: int | None = Field(default=None, description="The length of the stored inner HTML, in bytes as stored")
    mime_type: str | None = Field(default=None, description="The MIME type of the stored inner HTML: text/html")
    preview: str | None = Field(default=None, description="The first few hundred characters of the stored inner HTML, always its true start")

    def require_inner_html(self) -> str:
        """The inner HTML, held inline or loaded from storage.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its HTML that was never loaded.
        """
        # An HTML content's value is its `inner_html` field, or the markup loaded as it was stored, so it is always a `str`.
        return cast("str", self.require_value())

    @property
    @override
    def short_desc(self) -> str:
        if self.inner_html is None:
            return self._stored_short_desc()
        return f"some html ({len(self.inner_html)} chars)"

    @override
    def rendered_plain(self) -> str:
        return self.require_inner_html()

    @override
    def rendered_html(self) -> str:
        inner_html = self.require_inner_html()
        # If no css_class is provided, return raw inner_html without wrapping
        if not self.css_class:
            return inner_html
        template_source = '<div class="{{ css_class|e }}">{{ inner_html|safe }}</div>'
        return render_jinja2_sync(
            template_source=template_source,
            template_category=TemplateCategory.HTML,
            templating_context={
                "inner_html": inner_html,
                "css_class": self.css_class,
            },
        )

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return self.require_inner_html()

    @override
    def rendered_json(self) -> str:
        return kajson.dumps(self.rendered_value_form(), indent=4)

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> "PrettyPrintable":
        if not self.is_loaded:
            return self.rendered_reference_pretty()
        value_form = self.rendered_value_form()
        require_rich_for_rendering()
        from rich.json import JSON

        return JSON.from_data(value_form, indent=4)
