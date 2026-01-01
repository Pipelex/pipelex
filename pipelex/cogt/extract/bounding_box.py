from __future__ import annotations

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Bounding box coordinates for a rectangle in 2D space, typically to locate an image in a page."""

    top_left_x: float = Field(description="X coordinate of top-left corner")
    top_left_y: float = Field(description="Y coordinate of top-left corner")
    top_right_x: float = Field(description="X coordinate of top-right corner")
    top_right_y: float = Field(description="Y coordinate of top-right corner")
    bottom_right_x: float = Field(description="X coordinate of bottom-right corner")
    bottom_right_y: float = Field(description="Y coordinate of bottom-right corner")
    bottom_left_x: float = Field(description="X coordinate of bottom-left corner")
    bottom_left_y: float = Field(description="Y coordinate of bottom-left corner")

    @classmethod
    def make_from_two_corners(cls, top_left_x: float, top_left_y: float, bottom_right_x: float, bottom_right_y: float) -> BoundingBox:
        return BoundingBox(
            top_left_x=top_left_x,
            top_left_y=top_left_y,
            top_right_x=bottom_right_x,
            top_right_y=top_left_y,
            bottom_right_x=bottom_right_x,
            bottom_right_y=bottom_right_y,
            bottom_left_x=top_left_x,
            bottom_left_y=bottom_right_y,
        )
