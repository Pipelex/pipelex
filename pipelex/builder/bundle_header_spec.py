from pydantic import Field
from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.pretty import PrettyPrintable


class BundleHeaderSpec(StructuredContent):
    domain_code: str = Field(description="Name of the domain of the knowledge work.")
    description: str = Field(description="Definition of the domain of the knowledge work.")
    system_prompt: str | None = Field(description="System prompt for the domain.")
    main_pipe: str = Field(description="The main pipe of the domain.")

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        bundle_group = Group()
        if title:
            bundle_group.renderables.append(Text(title, style="bold"))
        bundle_group.renderables.append(Text.from_markup(f"Domain: [yellow]{self.domain_code}[/yellow]\n", style="bold"))
        bundle_group.renderables.append(Text.from_markup(f"Description: [yellow italic]{self.description}[/yellow italic]\n"))
        bundle_group.renderables.append(Text.from_markup(f"Main Pipe: [red]{self.main_pipe}[/red]\n"))
        if self.system_prompt:
            bundle_group.renderables.append(Text(f"System Prompt: {self.system_prompt}", style="dim"))

        return bundle_group
