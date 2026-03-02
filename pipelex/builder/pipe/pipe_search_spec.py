from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.talents.search_talent import SearchTalent
from pipelex.config import get_config
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable

if TYPE_CHECKING:
    from pipelex.cogt.search.search_setting import SearchModelChoice


class PipeSearchSpec(PipeSpec):
    """Specs for web search pipe operations in the Pipelex framework.

    PipeSearch enables web search using various search providers.
    Supports static and dynamic prompts with configurable search parameters.
    """

    type: Literal["PipeSearch"] = "PipeSearch"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    search_talent: SearchTalent | str = Field(
        description="Select the most adequate search talent according to the task to be performed.",
        examples=list(SearchTalent),
    )
    prompt: str = Field(description="A finalized search prompt or prompt template: use `$` prefix for inline variables (e.g., `$topic`).")

    @field_validator("search_talent", mode="before")
    @classmethod
    def validate_search_talent(cls, search_talent_value: str) -> SearchTalent:
        try:
            return SearchTalent(search_talent_value)
        except ValueError:
            valid = [talent.value for talent in SearchTalent]
            msg = f"'{search_talent_value}' is not a valid SearchTalent. Valid values: {valid}"
            raise ValueError(msg) from None

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with search-specific details
        search_group = Group()
        search_group.renderables.append(base_group)

        # Add search specific information
        search_group.renderables.append(Text())  # Blank line
        search_group.renderables.append(Text.from_markup(f"Search Talent: [bold yellow]{self.search_talent}[/bold yellow]"))
        search_group.renderables.append(Text.from_markup(f"Prompt: [bold cyan]{self.prompt}[/bold cyan]"))

        return search_group

    @override
    def to_blueprint(self) -> PipeSearchBlueprint:
        """Convert this PipeSearchSpec to the core PipeSearchBlueprint."""
        base_blueprint = super().to_blueprint()

        # Get search choice from config-based mapping
        mappings = get_config().pipelex.builder_config.talent_preset_mappings.search
        search_choice: SearchModelChoice = mappings[self.search_talent]

        return PipeSearchBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            prompt=self.prompt,
            model=search_choice,
            depth=None,
            include_images=None,
            max_results=None,
            from_date=None,
            to_date=None,
            include_domains=None,
            exclude_domains=None,
        )
