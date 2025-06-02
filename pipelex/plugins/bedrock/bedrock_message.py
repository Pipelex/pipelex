from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from pipelex.types import StrEnum

# Commented stuff below corresponds to untested stuff because Vision models are not available on Bedrock yet

# AWS docs:
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-runtime/client/converse.html


class ImageFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    # GIF = "gif"
    # WEBP = "webp"


# class DocumentFormat(str, Enum):
#     PDF = "pdf"
#     CSV = "csv"
#     DOC = "doc"
#     DOCX = "docx"
#     XLS = "xls"
#     XLSX = "xlsx"
#     HTML = "html"
#     TXT = "txt"
#     MD = "md"


# class VideoFormat(str, Enum):
#     MKV = "mkv"
#     MOV = "mov"
#     MP4 = "mp4"
#     WEBM = "webm"
#     FLV = "flv"
#     MPEG = "mpeg"
#     MPG = "mpg"
#     WMV = "wmv"
#     THREE_GP = "three_gp"


# class BedrockS3Location(BaseModel):
#     uri: str
#     bucketOwner: str


class BedrockSource(BaseModel):
    bytes: bytes
    # s3Location: Optional[BedrockS3Location] = None


class BedrockImage(BaseModel):
    format: ImageFormat
    source: BedrockSource


# class BedrockDocument(BaseModel):
#     format: DocumentFormat
#     name: str
#     source: BedrockSource


# class BedrockVideo(BaseModel):
#     format: VideoFormat
#     source: BedrockSource


# class BedrockToolUse(BaseModel):
#     toolUseId: str
#     name: str
#     input: Any


# class BedrockToolResultContent(BaseModel):
#     json_content: Optional[Any] = None
#     text: Optional[str] = None
#     image: Optional[BedrockImage] = None
#     document: Optional[BedrockDocument] = None
#     video: Optional[BedrockVideo] = None


# class BedrockToolResult(BaseModel):
#     toolUseId: str
#     content: List[BedrockToolResultContent]
#     status: Literal["success", "error"]


# class GuardContentText(BaseModel):
#     text: str
#     qualifiers: List[Literal["grounding_source", "query", "guard_content"]]


# class GuardContent(BaseModel):
#     text: Optional[GuardContentText] = None
#     image: Optional[BedrockImage] = None


class BedrockContentItem(BaseModel):
    text: Optional[str] = None
    image: Optional[BedrockImage] = None
    # document: Optional[BedrockDocument] = None
    # video: Optional[BedrockVideo] = None
    # toolUse: Optional[BedrockToolUse] = None
    # toolResult: Optional[BedrockToolResult] = None
    # guardContent: Optional[GuardContent] = None


BedrockMessageDict = Dict[str, Any]
BedrockMessageDictList = List[BedrockMessageDict]


class BedrockMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: List[BedrockContentItem]

    def to_dict(self) -> BedrockMessageDict:
        return self.model_dump(exclude_none=True)

    def to_dict_list(self) -> BedrockMessageDictList:
        return [self.to_dict()]
