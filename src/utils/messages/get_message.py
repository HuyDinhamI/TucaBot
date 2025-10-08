

from typing import Optional
import logging
from langchain_core.messages import (
    BaseMessage, AIMessage, HumanMessage, ToolMessage
)

from src.state import AgentState
from src.schemas import ConversationMessage

logger = logging.getLogger(__name__)

def get_conversation_history(
    state: AgentState,
    include_user: bool = True,
    include_ai: bool = True,
    include_tool: bool = True,
    tool_names: Optional[list[str]] = None,
    human_message_words_limit: Optional[int] = None,
    ai_message_words_limit: Optional[int] = None,
    tool_message_words_limit: Optional[int] = None,
    include_file_content: bool = False,
    include_file_tag: bool = True,
    **kwargs
):
    """Get history conversation before the latest user message."""
    history: list[ConversationMessage] = []
    start_history: bool = False

    for msg in state["messages"][::-1]:
        if start_history and isinstance(msg, AIMessage) and include_ai:
            content = get_text_message(
                msg,
                max_words=ai_message_words_limit
            )
            if content:
                history.append(ConversationMessage(
                    role="assistant",
                    content=content
                ))

        elif isinstance(msg, HumanMessage):
            if start_history and include_user:
                content = get_text_message(
                    msg,
                    include_file_content=include_file_content,
                    include_file_tag=include_file_tag,
                    max_words=human_message_words_limit
                )
                if content:
                    history.append(ConversationMessage(
                        role="user",
                        content=content
                    ))

            start_history = True

        elif start_history and isinstance(msg, ToolMessage) and include_tool and \
            (tool_names is None or msg.name in tool_names):
            content = get_text_message(
                msg,
                max_words=tool_message_words_limit,
            )
            if msg.name:
                content = f"{msg.name}\n{content}"
            if content:
                history.append(ConversationMessage(
                    role="tool",
                    content=content,
                    name=msg.name
                ))
    return history[::-1]

def get_latest_user_message(
    state: AgentState,
    include_file_content: bool = False,
    include_file_tag: bool = True,
    max_words: Optional[int] = None
) -> Optional[str]:
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return get_text_message(
                msg,
                include_file_content=include_file_content,
                include_file_tag=include_file_tag,
                max_words=max_words
            )

def get_tool_messages(
    state: AgentState,
    turns_limit: Optional[int] = None,
    tool_names: Optional[list[str]] = None
) -> list[str]:
    contents: list[str] = []
    for msg in reversed(state["messages"]):
        if isinstance(msg, ToolMessage) and msg.content:
            if tool_names and msg.name not in tool_names:
                continue
            contents.append(msg.content)
            if turns_limit and len(contents) == turns_limit:
                break
    return list(reversed(contents))

def get_text_message(
    message: BaseMessage,
    include_file_content: bool = False,
    include_file_tag: bool = True,
    max_words: Optional[int] = None,
    **kwargs
) -> str:
    """Get text content from a message, handling different types of content."""
    content = message.content

    if isinstance(content, str):
        return truncate_message(content, max_words)

    if isinstance(content, dict):
        content = [content]
    
    file_contents: list[str] = []
    texts: list[str] = []
    for item in content:
        if (
            isinstance(item, dict) and
            item.get("type") == "text" and
            item.get("text")
        ):
            texts.append(truncate_message(item.get("text"), max_words))

        elif (
            isinstance(item, dict) and
            item.get("type") in ["pdf", "doc", "docx", "txt", "jpeg", "png", "jpg", "image"]
        ):
            file_type = item.get("type")
            if include_file_content:
                file_content = item.get("file", {}).get("file_content", "")
                file_contents.append(f"<{file_type}-attached-file-content>\n{file_content}\n</>")
            elif include_file_tag:
                file_contents.append(f"<{file_type}-attached-file-content>content...</>")
    
    return ("\n".join(file_contents) + "\n" + "\n".join(texts)).strip()

def get_text_message_list(
    message: BaseMessage,
    include_file_content: bool = False,
    include_file_tag: bool = True,
    **kwargs
) -> dict:
    content = message.content
    
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        content = [content]

    texts: list[str] = []
    file_texts: list[str] = []
    for item in content:
        if (
            isinstance(item, dict) and
            item.get("type") == "text" and
            item.get("text")
        ):
            texts.append(item.get("text"))

        elif (
            isinstance(item, dict) and
            item.get("type") in ["pdf", "doc", "docx", "txt", "jpeg", "png", "jpg", "image"] and
            include_file_content
        ):
            # file_id = item.get("file", {}).get("file_id")
            # file_name = item.get("file", {}).get("filename")
            # file_content = get_file_content_from_file_id(file_id, item.get("type"), file_name)
            file_content = item.get("file", {}).get("file_content", "")
            file_texts.append(f"<attached-file-content>\n{file_content}\n</attached-file-content>")

    message_dict = {
        "text": "\n".join(texts).strip(),
        "files_content": file_texts
    }
    
    return message_dict

def truncate_message(
    message: str, max_words: Optional[int] = None
) -> str:
    if max_words is None:
        return message
    words = message.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return message
