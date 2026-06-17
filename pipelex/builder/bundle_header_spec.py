from pydantic import Field
from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.cogt.content_generation.dry_mock import MOCK_MAIN_PIPE_CODE
from pipelex.cogt.content_generation.dry_run_factory import MockFormat
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.pretty import PrettyPrintable


class BundleHeaderSpec(StructuredContent):
    domain_code: str = Field(description="Name of the domain of the knowledge work.", json_schema_extra={"mock_format": MockFormat.SNAKE_CASE})
    description: str = Field(description="Definition of the domain of the knowledge work.")
    system_prompt: str | None = Field(description="System prompt for the domain.")
    # The example IS the dry-run coordination: mocked headers name MOCK_MAIN_PIPE_CODE as the
    # bundle's main pipe, and stamp_mock_main_coordination makes mocked pipe-spec lists answer to it.
    main_pipe: str = Field(description="The main pipe of the domain.", examples=[MOCK_MAIN_PIPE_CODE])

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        bundle_group = Group()
        if title:
            bundle_group.renderables.append(Text(title, style="bold"))
        bundle_group.renderables.append(Text.from_markup(f"Domain: [yellow]{self.domain_code}[/yellow]\n", style="bold"))
        bundle_group.renderables.append(Text.from_markup(f"Description: [yellow italic]{self.description}[/yellow italic]\n"))
        bundle_group.renderables.append(Text.from_markup(f"Main Pipe: [red]{self.main_pipe}[/red]\n"))
        if self.system_prompt:
            bundle_group.renderables.append(Text(f"System Prompt: {self.system_prompt}", style="dim"))

        return bundle_group
