from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class Document(StructuredContent):
    text: str = Field(..., description="The full document text containing multiple customer reviews")
    title: str = Field(default="", description="Optional title of the document")


class CustomerReview(StructuredContent):
    review_text: str = Field(..., description="The customer review text")
    rating: int = Field(default=0, description="Optional numerical rating (1-5)")
    reviewer_name: str = Field(default="", description="Optional reviewer name")


class SentimentAnalysis(StructuredContent):
    sentiment: str = Field(..., description="Sentiment classification (positive/negative/neutral)")
    confidence_score: float = Field(..., description="Confidence score for the sentiment analysis (0-1)")
    summary: str = Field(default="", description="Brief summary of the sentiment analysis")


class ProductRating(StructuredContent):
    overall_rating: float = Field(..., description="Overall product rating from 1-5 stars")
    total_reviews: int = Field(..., description="Total number of reviews analyzed")
    explanation: str = Field(..., description="Explanation of how the rating was determined")
    positive_count: int = Field(default=0, description="Number of positive reviews")
    negative_count: int = Field(default=0, description="Number of negative reviews")
    neutral_count: int = Field(default=0, description="Number of neutral reviews")
