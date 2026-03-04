import re
from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from rich.console import Group
from rich.panel import Panel
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
    from_date: str | None = Field(
        default=None,
        description="Start date filter in ISO 8601 format (YYYY-MM-DD). Only return results from this date onwards.",
    )
    to_date: str | None = Field(
        default=None,
        description="End date filter in ISO 8601 format (YYYY-MM-DD). Only return results up to this date.",
    )
    include_domains: list[str] | None = Field(default=None, description="Restrict search to these domains only (e.g., ['reuters.com', 'bbc.com']).")
    exclude_domains: list[str] | None = Field(default=None, description="Exclude results from these domains.")

    @field_validator("from_date", "to_date", mode="before")
    @classmethod
    def validate_date_format(cls, date_value: str | None) -> str | None:
        if date_value is None:
            return date_value
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            msg = f"'{date_value}' is not a valid date (expected YYYY-MM-DD)"
            raise ValueError(msg)
        return date_value

    @field_validator("search_talent", mode="before")
    @classmethod
    def validate_search_talent(cls, search_talent_value: str) -> SearchTalent:
        try:
            return SearchTalent(search_talent_value)
        except ValueError:
            valid = list(SearchTalent)
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
        prompt_panel = Panel(
            self.prompt,
            title="Search Prompt",
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
        )
        search_group.renderables.append(Text())  # Blank line
        search_group.renderables.append(prompt_panel)

        # Show filter fields when set
        filter_lines: list[str] = []
        if self.from_date is not None:
            filter_lines.append(f"From date: {self.from_date}")
        if self.to_date is not None:
            filter_lines.append(f"To date: {self.to_date}")
        if self.include_domains is not None:
            filter_lines.append(f"Include domains: {', '.join(self.include_domains)}")
        if self.exclude_domains is not None:
            filter_lines.append(f"Exclude domains: {', '.join(self.exclude_domains)}")
        if filter_lines:
            search_group.renderables.append(Text())  # Blank line
            for filter_line in filter_lines:
                search_group.renderables.append(Text.from_markup(f"[dim]{filter_line}[/dim]"))

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
            include_images=None,
            max_results=None,
            from_date=self.from_date,
            to_date=self.to_date,
            include_domains=self.include_domains,
            exclude_domains=self.exclude_domains,
        )
