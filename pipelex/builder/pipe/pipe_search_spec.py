import re
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from rich.console import Group
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeSearchSpec(PipeSpec):
    """Specs for web search pipe operations in the Pipelex framework.

    PipeSearch enables web search using various search providers.
    Supports static and dynamic prompts with configurable search parameters.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["PipeSearch"] = "PipeSearch"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    model: str | None = Field(
        default=None,
        description="Model preset, alias, waterfall, or direct model handle. Use presets from 'pipelex-agent models'.",
    )
    prompt: str = Field(
        validation_alias="query",
        description="A finalized search prompt or prompt template: use `$` prefix for inline variables (e.g., `$topic`).",
    )
    from_date: str | None = Field(
        default=None,
        description="Start date filter in ISO 8601 format (YYYY-MM-DD). Only return results from this date onwards.",
        examples=["2025-01-01"],
    )
    to_date: str | None = Field(
        default=None,
        description="End date filter in ISO 8601 format (YYYY-MM-DD). Only return results up to this date.",
        examples=["2025-01-01"],
    )
    include_domains: list[str] | None = Field(default=None, description="Restrict search to these domains only (e.g., ['reuters.com', 'bbc.com']).")
    exclude_domains: list[str] | None = Field(default=None, description="Exclude results from these domains.")
    max_results: int | None = Field(
        default=None, description="Maximum number of search results to return. If not set, the search provider's default is used."
    )

    @field_validator("model", mode="before")
    @classmethod
    def reject_empty_model(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            msg = "Model cannot be an empty string; omit the field to use defaults"
            raise ValueError(msg)
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_prompt_field(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Accept both 'prompt' and 'query' as input field names.

        The LLM may generate 'query' instead of 'prompt', so we normalize 'prompt' to 'query'
        which is the validation_alias that Pydantic expects.
        """
        if "prompt" in values and "query" not in values:
            values["query"] = values.pop("prompt")
        return values

    @field_validator("from_date", "to_date", mode="before")
    @classmethod
    def validate_date_format(cls, date_value: str | None) -> str | None:
        if date_value is None:
            return date_value
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
            msg = f"'{date_value}' is not a valid date (expected YYYY-MM-DD)"
            raise ValueError(msg)
        return date_value

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with search-specific details
        search_group = Group()
        search_group.renderables.append(base_group)

        # Add search specific information
        search_group.renderables.append(Text())  # Blank line
        search_group.renderables.append(Text.from_markup(f"Model: [bold yellow]{escape(self.model or '(default)')}[/bold yellow]"))
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
        if self.max_results is not None:
            filter_lines.append(f"Max results: {self.max_results}")
        if filter_lines:
            search_group.renderables.append(Text())  # Blank line
            for filter_line in filter_lines:
                search_group.renderables.append(Text.from_markup(f"[dim]{filter_line}[/dim]"))

        return search_group

    @override
    def to_blueprint(self) -> PipeSearchBlueprint:
        """Convert this PipeSearchSpec to the core PipeSearchBlueprint."""
        base_blueprint = super().to_blueprint()

        return PipeSearchBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            prompt=self.prompt,
            model=self.model,
            include_images=None,
            max_results=self.max_results,
            from_date=self.from_date,
            to_date=self.to_date,
            include_domains=self.include_domains,
            exclude_domains=self.exclude_domains,
        )
