from pydantic import BaseModel, Field


class GatewaySearchRequestParams(BaseModel):
    """Parameters for a web search request sent to the relay."""

    query: str = Field(description="The search query text")
    depth: str = Field(default="standard", description="Search depth: 'standard' or 'deep'")
    include_images: bool = Field(default=False, description="Whether to include images in results")
    include_inline_citations: bool = Field(default=True, description="Whether to include inline citations")
    max_results: int | None = Field(default=None, description="Maximum number of results to return")
    include_domains: list[str] | None = Field(default=None, description="Restrict search to these domains")
    exclude_domains: list[str] | None = Field(default=None, description="Exclude these domains from search")
    from_date: str | None = Field(default=None, description="Start date filter (YYYY-MM-DD)")
    to_date: str | None = Field(default=None, description="End date filter (YYYY-MM-DD)")
    output_schema: dict[str, object] | None = Field(default=None, description="JSON Schema for structured search output")


class GatewayFetchRequestParams(BaseModel):
    """Parameters for a web page fetch request sent to the relay."""

    url: str = Field(description="The URL to fetch")
    include_raw_html: bool | None = Field(default=None, description="Whether to include raw HTML in response")
    render_js: bool | None = Field(default=None, description="Whether to render JavaScript before fetching")
    extract_images: bool | None = Field(default=None, description="Whether to extract images from the page")
    timeout: float | None = Field(default=None, description="Request timeout in seconds")
