from typing import Optional, Literal
from pydantic import BaseModel

class ConversationMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    name: Optional[str] = None  # For tool messages, e.g., "search_tool"
    
    def to_dict(self):
        return {"role": self.role, "content": self.content, "name": self.name}
