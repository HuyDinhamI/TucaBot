import hashlib
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, model_validator, field_validator, computed_field
from langchain_core.documents import Document


class DocumentChunk(BaseModel):
    """Schema for document chunk data"""

    id: Optional[str] = Field(
        default=None,
        description="Unique identifier of the document chunk",
    )
    title: Optional[str] = Field(default="", description="Title of the chunk")
    content: str = Field(description="Text content of the chunk")
    document_id: str = Field(
        default=None,
        description="ID of the document that this chunk belongs to"
    )
    app_ids: List[str] = Field(
        default=[],
        description="List of application IDs that this chunk is associated with"
    )
    misa_id: Optional[str] = Field(
        default=None,
        description="Unique identifier of the user who created this chunk"
    )
    tenant_id: str = Field(
        default=None,
        description="ID of the organization (Tenant) owning this chunk"
    )
    chunk_index: int = Field(
        default=0,
        description="Sequential position index of the chunk in the original document"
    )
    hit_count: int = Field(
        default=0,
        description="Number of times this chunk has been found in search results",
    )
    enabled: bool = Field(
        default=True,
        description="Activation status of the chunk (True = disabled, False = enabled)",
    )
    embedding_status: bool = Field(
        default=None,
        description="Current status of the chunk (True = success, False = failed)",
    )
    published: bool = Field(
        default=False,
        description="Publish status of the chunk (True = published, False = draft)",
    )
    document_metadata: Optional[Dict] = Field(
        {},
        description="Document metadata including name, data source type, file ID, etc."
    )

    # Validate and convert UUID strings
    @field_validator("id", "tenant_id", "document_id")
    @classmethod
    def validate_uuid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            # Verify it's a valid UUID by attempting to parse it
            UUID(v)
            return v
        except ValueError:
            raise ValueError("Invalid UUID string")

    @model_validator(mode="after")
    def set_defaults(self) -> "DocumentChunk":
        if self.id is None:
            self.id = str(uuid4())
        if self.document_id is None:
            self.document_id = str(uuid4())
    
    @computed_field
    @property
    def content_hash(self) -> str:
        """Dynamically computed content hash based on title and content"""
        title = self.title or ""
        content = self.content or ""
        combined_content = str(title) + "\n" + str(content)
        return hashlib.md5(combined_content.encode()).hexdigest()
    
    @computed_field
    @property
    def char_count(self) -> str:
        """Dynamically computed char_count based on title and content"""
        title = self.title or ""
        content = self.content or ""
        combined_content = str(title) + "\n" + str(content)
        return len(combined_content)
    class Config:
        validate_assignment = True
    
    @classmethod
    def extract_from_metadata(cls, data: Any) -> Any:
        """Extract fields from metadata if data comes from ORM and return DocumentChunk instance"""
        if isinstance(data, dict) and "metadata" in data:
            metadata = data.get("metadata", {})
            # Return a DocumentChunk instance with combined data
            return cls(**metadata)
    
    def to_langchain_model(self) -> Document:
        """Convert to langchain model format"""
        # Tạo dict cho metadata
        metadata = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "document_id": self.document_id,
            "app_ids": self.app_ids,
            "misa_id": self.misa_id,
            "chunk_index": self.chunk_index,
            "title": self.title,
            "content": self.content,
            "content_hash": self.content_hash,
            "char_count": self.char_count,
            "hit_count": self.hit_count,
            "enabled": self.enabled,
            "embedding_status": self.embedding_status,
            "document_metadata": self.document_metadata,
        }
        content = self.title + "\n" + self.content
        document = Document(
            id=self.id,
            page_content=content,
            metadata=metadata
        )

        return document


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
    app_ids: List[str] = Field(
        default=[],
        description="List of application IDs that this chunk is associated with"
    )
    misa_id: Optional[str] = Field(
        default=None,
        description="Unique identifier of the user who created this chunk"
    )
    tenant_id: Optional[str] = Field(
        default=None,
        description="ID of the organization (Tenant) owning this chunk"
    )
    document_id: Optional[str] = Field(
        default=None,
        description="ID of the document that this chunk belongs to"
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