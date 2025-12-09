from enum import Enum
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, model_validator
from src.ai_core.models.chunks import DocumentChunk

class Status(Enum):
    UNPUBLISHED = 0
    PUBLISHED = 1
    DISABLED = 2
    ENABLED = 3

class GetChunkResponse(BaseModel):
    chunks: List[dict[str, Any]]
    total: int

class CreateChunkRequest(BaseModel):
    """Schema for chunk creation request"""

    id: str = Field(
        description="Unique identifier of the document chunk, id is a string UUID",
    )
    title: Optional[str] = Field(default="", description="Title of the chunk")
    content: str = Field(description="Text content of the chunk")
    app_ids: List[str] = Field(
        default=[],
        description="List of application IDs that this chunk is associated with"
    )
    chunk_index: int = Field(
        default=0,
        description="Sequential position index of the chunk in the original document",
    )
    document_metadata: Optional[Dict] = Field(
        {},
        description="Document metadata including name, data source type, file ID, etc.",
    )
    
    def to_db_model(self, embedding_status) -> DocumentChunk:
        """Convert to db model format"""
        document = DocumentChunk(
            app_ids=self.app_ids,
            id=self.id,
            title=self.title,
            content=self.content,
            chunk_index=self.chunk_index,
            embedding_status=embedding_status,
            document_metadata=self.document_metadata
        )

        return document


class UpdateChunkRequest(BaseModel):
    """Schema for chunk update request"""

    id: str = Field(
        description="Unique identifier of the document chunk, id is a string UUID",
    )
    title: Optional[str] = Field(default=None, description="Title of the chunk")
    content: Optional[str] = Field(default=None, description="Text content of the chunk")

class OperationChunkResponse(BaseModel):
    success_ids: List[str]
    failed_ids: List[str]

class SearchRequest(BaseModel):
    query: str = Field(
        description="The search query string from the user",
        min_length=1
    )
    top_k: int = Field(
        default=5,
        description="Maximum number of results to return",
        ge=1,
        le=100
    )
    score_threshold: float = Field(
        default=0.5,
        description="Minimum score threshold for accepting results",
        ge=0.0,
        le=1.0
    )
    
class SearchResult(BaseModel):
    id: Optional[str] = Field(
        default=None,
        description="Unique identifier of the document chunk",
    )
    title: Optional[str] = Field(default="", description="Title of the chunk")
    content: str = Field(description="Text content of the chunk")
    score : float = Field(
        default=0.0,
        description="Score of the document chunk"
    )
    chunk_index: Optional[int] = Field(
        default=0,
        description="Sequential position index of the chunk in the original document"
    )
    url: Optional[str] = Field(
        default=None,
        description="URL of the document chunk"
    )
    document_metadata: Optional[Dict] = Field(
        {},
        description="Document metadata including name, data source type, file ID, etc."
    )
