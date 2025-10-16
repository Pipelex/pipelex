from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class BundleHeaderSpec(StructuredContent):
    domain: str = Field(description="Name of the domain of the knowledge work.")
    description: str = Field(description="Definition of the domain of the knowledge work.")
    system_prompt: str | None = Field(description="System prompt for the domain.")
    main_pipe: str = Field(description="The main pipe of the domain.")
