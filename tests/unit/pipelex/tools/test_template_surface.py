"""The declarations the template sandbox reads: a type's template surface, and whether a type implements a rendering protocol."""

import pytest
from jinja2.utils import Namespace

from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.image_renderable import ImageRenderable
from pipelex.tools.jinja2.renderable_dispatch import type_implements
from pipelex.tools.jinja2.tag_renderable import TagRenderable
from pipelex.tools.jinja2.template_surface import TemplateSurface
from pipelex.tools.jinja2.text_format_renderable import TextFormatRenderable


class _HoldsRenderMethodAsData:
    def __init__(self) -> None:
        self.render_with_images = print


class TestTemplateSurface:
    @pytest.mark.parametrize("name", ["__class__", "stuff_name"])
    def test_private_names_are_single_underscore_names(self, name: str) -> None:
        with pytest.raises(ValueError, match="single underscore"):
            TemplateSurface(callable_names=frozenset(), private_names=frozenset({name}))

    @pytest.mark.parametrize(
        ("value", "protocol"),
        [(ImageContent(url="https://example.com/photo.png"), ImageRenderable), (TextContent(text="hello"), TextFormatRenderable)],
    )
    def test_a_class_defining_the_protocol_implements_it(self, value: object, protocol: type) -> None:
        assert type_implements(value=value, protocol=protocol)

    @pytest.mark.parametrize(
        ("topic", "value", "protocol"),
        [
            ("instance_attribute", _HoldsRenderMethodAsData(), ImageRenderable),
            ("namespace", Namespace(render_with_images=print), ImageRenderable),
            ("namespace_with_every_member", Namespace(render_for_tag_async=print, default_tag_name="x"), TagRenderable),
            ("plain_value", "text", TextFormatRenderable),
        ],
    )
    def test_members_held_by_an_instance_do_not_implement_it(self, topic: str, value: object, protocol: type) -> None:
        assert not type_implements(value=value, protocol=protocol), topic
