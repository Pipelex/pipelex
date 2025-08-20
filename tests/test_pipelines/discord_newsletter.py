from typing import List

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent


class Attachment(StructuredContent):
    """Represents a Discord message attachment"""

    name: str = Field(..., description="Name of the attachment file")
    url: str = Field(..., description="URL of the attachment")


class Embed(StructuredContent):
    """Represents a Discord message embed"""

    title: str = Field(..., description="Title of the embed")
    description: str = Field(..., description="Description of the embed content")
    type: str = Field(..., description="Type of the embed (e.g., article, video)")


class DiscordMessage(StructuredContent):
    """Represents a Discord message within a channel"""

    author: str = Field(..., description="Author of the message")
    content: str = Field(..., description="Content of the message")
    attachments: List[Attachment] = Field(default_factory=list, description="List of message attachments")
    embeds: List[Embed] = Field(default_factory=list, description="List of message embeds")
    link: str = Field(..., description="Link to the message")


class DiscordChannelUpdate(StructuredContent):
    """Represents a Discord channel with its messages"""

    name: str = Field(..., description="Name of the Discord channel")
    position: int = Field(..., description="Position of the channel")
    messages: List[DiscordMessage] = Field(default_factory=list, description="List of messages in the channel")


class ChannelSummary(StructuredContent):
    """Represents a summarized Discord channel for newsletter inclusion"""

    channel_name: str = Field(..., description="Name of the Discord channel")
    summary_items: List[str] = Field(..., description="Well-written summaries of the channel's activity")


class Newsletter(StructuredContent):
    """Represents the final newsletter content"""

    weekly_summary: str = Field(..., description="200 character summary of weekly Share channel content")
    new_members: List[str] = Field(default_factory=list, description="New member introductions in bullet points")
    channel_sections: List[ChannelSummary] = Field(default_factory=list, description="Ordered channel summaries")
    geographic_hubs: List[ChannelSummary] = Field(default_factory=list, description="Geographic hub channels grouped at end")
