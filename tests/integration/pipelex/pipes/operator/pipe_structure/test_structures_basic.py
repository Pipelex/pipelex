"""Test structures for PipeStructure integration tests."""

from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class SimpleResult(StructuredContent):
    """A small structured result for PipeStructure tests."""

    title: str = Field(..., description="The title field")
    score: int = Field(..., description="A score")


class RestaurantReview(StructuredContent):
    """A richer structured review of a restaurant, used by the PipeStructure e2e tests."""

    name: str = Field(..., description="Restaurant name")
    cuisine: str = Field(..., description="Type of cuisine, e.g. 'Neapolitan pizza' or 'Sichuan'")
    city: str = Field(..., description="City the restaurant is in")
    overall_rating: int = Field(..., description="Overall rating from 1 (poor) to 10 (outstanding)")
    price_range: str = Field(..., description="Approximate price level expressed as '$', '$$', '$$$', or '$$$$'")
    standout_dishes: list[str] = Field(..., description="Memorable dishes worth ordering")
    caveats: list[str] = Field(..., description="Downsides or things to be aware of")
    one_line_take: str = Field(..., description="A single-sentence summary of the review")
