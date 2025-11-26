from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class OptimizedTweet(StructuredContent):
    """A tweet optimized for Twitter/X engagement following best practices."""

    lead_tweet: str
    follow_up_tweets: list[str] | None = Field(default_factory=list[str])
