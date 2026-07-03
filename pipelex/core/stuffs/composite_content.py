import html as html_module
from typing import Any, cast

from pydantic import ConfigDict
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.markdown_utils import convert_to_markdown


class CompositeContent(StuffContent):
    """Untyped named composition of contents — the structure class of `native.Composite`.

    Holds its named sub-contents as top-level fields (pydantic `extra="allow"`), so the
    serialized shape matches a bespoke structured concept: `{name: content, ...}` with no
    wrapper key. This is the combination vehicle for a `PipeParallel` whose author does not
    want to declare a bespoke concept: each branch's `result` name becomes a field.
    """

    model_config = ConfigDict(extra="allow")

    @property
    def components(self) -> dict[str, Any]:
        """Named sub-contents of this composite, keyed by their given names."""
        return dict(self.model_extra or {})

    def __json_encode__(self) -> dict[str, Any]:  # noqa: PLW3201 — kajson encoder hook, name fixed by kajson's protocol
        """Kajson encoding hook.

        Pydantic stores `extra="allow"` fields outside `__dict__`, so kajson's default
        `__dict__` fallback would silently drop every component. Handing kajson the live
        components lets it recursively encode each one with its own class metadata, so a
        kajson round-trip rebuilds typed sub-contents.
        """
        return self.components

    @property
    @override
    def short_desc(self) -> str:
        component_names = ", ".join(self.components) or "nothing"
        return f"composite of {component_names}"

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return convert_to_markdown(data=self.smart_dump(), level=level, is_pretty=is_pretty)

    @override
    def rendered_html(self) -> str:
        rows: list[str] = []
        for component_name, component_value in self.components.items():
            rendered_value = self._render_component_html(component_value)
            rows.append(f"<tr><th>{html_module.escape(component_name)}</th><td>{rendered_value}</td></tr>")
        if not rows:
            return "<table><tr><td><em>empty</em></td></tr></table>"
        return f"<table>{''.join(rows)}</table>"

    def _render_component_html(self, value: Any) -> str:
        match value:
            case StuffContent():
                return value.rendered_html()
            case str():
                return html_module.escape(value)
            case dict():
                dict_value = cast("dict[str, Any]", value)
                items = [f"<dt>{html_module.escape(str(key))}</dt><dd>{self._render_component_html(val)}</dd>" for key, val in dict_value.items()]
                return f"<dl>{''.join(items)}</dl>"
            case list() | tuple():
                list_value = cast("list[Any]", value)
                items = [f"<li>{self._render_component_html(item)}</li>" for item in list_value]
                return f"<ul>{''.join(items)}</ul>"
            case _:
                return html_module.escape(str(value))
