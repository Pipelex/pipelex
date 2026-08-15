"""`TemplateBlueprint` rejects unknown keys, directly and through the `PipeCompose` authoring surface.

The rich `[pipe.name.template]` table is authored by hand; a misspelled `templating_style` or
`extra_context` used to be dropped silently, which yields a template rendered under a style or
context the author never asked for. It is a validation error now, like every other blueprint.
"""

from typing import Any

import pytest
from kajson import kajson
from pydantic import ValidationError

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_BASE_COMPOSE_TABLE: dict[str, Any] = {
    "description": "template blueprint strictness test",
    "inputs": {"name": "native.Text"},
    "output": "native.Text",
}


class TestTemplateBlueprintStrictness:
    def test_misspelled_templating_style_is_rejected(self):
        with pytest.raises(ValidationError, match="templating_stile"):
            TemplateBlueprint.model_validate({"template": "Hello @name", "category": "basic", "templating_stile": {"tag_style": "xml"}})

    def test_misspelled_extra_context_is_rejected(self):
        with pytest.raises(ValidationError, match="extra_contxt"):
            TemplateBlueprint.model_validate({"template": "Hello @name", "category": "basic", "extra_contxt": {"tone": "warm"}})

    def test_well_formed_table_still_parses(self):
        blueprint = TemplateBlueprint.model_validate(
            {
                "template": "Hello @name",
                "category": "markdown",
                "templating_style": {"tag_style": "xml", "text_format": "markdown"},
                "extra_context": {"tone": "warm"},
            }
        )
        assert blueprint.category == TemplateCategory.MARKDOWN
        assert blueprint.templating_style == TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.MARKDOWN)
        assert blueprint.extra_context == {"tone": "warm"}

    def test_misspelled_key_is_rejected_through_pipe_compose_blueprint(self):
        with pytest.raises(ValidationError, match="templating_stile"):
            PipeComposeBlueprint.model_validate(
                {
                    **_BASE_COMPOSE_TABLE,
                    "template": {"template": "Hello @name", "category": "basic", "templating_stile": {"tag_style": "xml"}},
                }
            )

    def test_misspelled_nested_style_key_is_rejected_through_pipe_compose_blueprint(self):
        with pytest.raises(ValidationError, match="text_formt"):
            PipeComposeBlueprint.model_validate(
                {
                    **_BASE_COMPOSE_TABLE,
                    "template": {"template": "Hello @name", "category": "basic", "templating_style": {"tag_style": "xml", "text_formt": "markdown"}},
                }
            )

    def test_kajson_round_trip_survives_strictness(self):
        blueprint = TemplateBlueprint(
            template="Hello @name",
            category=TemplateCategory.MARKDOWN,
            templating_style=TemplatingStyle(tag_style=TagStyle.XML, text_format=TextFormat.MARKDOWN),
            extra_context={"tone": "warm"},
        )
        assert kajson.loads(kajson.dumps(blueprint)) == blueprint
