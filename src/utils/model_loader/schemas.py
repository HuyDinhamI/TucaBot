from typing import Optional, Any
from pydantic import BaseModel
from langchain_core.messages.tool import ToolCall

class ModelResponseMetadata(BaseModel):
    model_name: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    ttft: Optional[float] = None
    ttlt: Optional[float] = None
    error_message: Optional[str] = None

class ChatResponse(BaseModel):
    content: Optional[str] = None
    thought: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    metadata: Optional[ModelResponseMetadata] = None

class StructuredResponse(BaseModel):
    content: Optional[Any] = None
    metadata: Optional[ModelResponseMetadata] = None