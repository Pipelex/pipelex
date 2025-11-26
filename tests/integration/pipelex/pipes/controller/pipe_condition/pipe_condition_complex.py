from typing import Literal

from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class DocumentRequest(StructuredContent):
    """Document processing request with comprehensive metadata."""

    document_type: Literal["technical", "business", "legal"] = Field(..., description="Type of document to be processed")
    priority: Literal["urgent", "normal", "low"] = Field(..., description="Processing priority level")
    language: Literal["english", "spanish", "french", "german", "chinese"] = Field(..., description="Document language")
    complexity: Literal["low", "medium", "high"] = Field(..., description="Document complexity level")


class UserProfile(StructuredContent):
    """User profile information for document processing context."""

    user_level: Literal["beginner", "intermediate", "expert"] = Field(..., description="User's expertise level")
    department: Literal["finance", "marketing", "legal", "technical", "operations"] = Field(..., description="User's department")


class ProcessingContext(StructuredContent):
    """Combined processing context for complex routing decisions."""

    document_request: DocumentRequest = Field(..., description="The document processing request")
    user_profile: UserProfile = Field(..., description="The user's profile information")

    @property
    def routing_key(self) -> str:
        """Generate a routing key based on combined context."""
        return f"{self.document_request.document_type}_{self.document_request.priority}_{self.user_profile.department}"
