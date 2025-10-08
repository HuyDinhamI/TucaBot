import math
from typing import List, Dict, Any, Tuple
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage
)
from langchain_core.messages.utils import (
    convert_to_messages,
    _get_message_openai_role
)

def trim_messages(
    messages: List[BaseMessage], 
    max_tokens: int = 128_000,
    keep_multi_turns: bool = True
) -> List[BaseMessage]:
    """
    Trim messages để giữ trong giới hạn tokens cho phép.
    
    Args:
        messages: Danh sách BaseMessage cần trim
        max_tokens: Số tokens tối đa cho phép (mặc định 128,000)
    
    Returns:
        Danh sách BaseMessage đã được trim
    
    Logic:
    1. Không cắt system messages
    2. Cắt theo chat turns (1 turn = từ HumanMessage đến trước HumanMessage tiếp theo)
    3. Ưu tiên turns mới nhất đến cũ nhất
    4. Nếu turn vừa đủ tokens: giữ toàn bộ turn
    5. Nếu turn quá lớn: chỉ giữ HumanMessage đầu tiên và AIMessage cuối cùng
    6. Giữ tối thiểu 1 turn chat (trim ToolMessages nếu cần)
    """
    if not messages:
        return messages
    
    if keep_multi_turns:
        pass
    else:
        messages = _get_latest_turn(messages)
    
    total_tokens = count_tokens_approximately(messages)
    
    # Nếu tổng tokens dưới giới hạn, return nguyên
    if total_tokens <= max_tokens:
        return messages
    
    # Trim theo chat turns
    return _trim_by_chat_turns(messages, max_tokens)

def _trim_by_chat_turns(
    messages: List[BaseMessage], max_tokens: int
) -> List[BaseMessage]:
    """
    Trim messages theo từng chat turn, ưu tiên giữ turn mới nhất.
    """
    analysis = _analyze_messages_by_tokens(messages)
    
    # Giữ tất cả system messages
    result = []
    system_tokens = 0
    for i in analysis["system_messages"]:
        result.append(messages[i])
        msg = messages[i]
        if hasattr(msg, "content") and msg.content:
            system_tokens += len(str(msg.content)) // 3
    
    remaining_tokens = max_tokens - system_tokens
    
    # Nếu system messages đã vượt quá giới hạn, chỉ giữ system messages
    if remaining_tokens <= 0:
        return result
    
    # Thêm chat turns từ cuối lên đầu (newest first)
    chat_turns = analysis["chat_turns"]
    selected_turn_messages = []
    
    for turn in reversed(chat_turns):
        turn_messages = messages[turn["start_idx"]:turn["end_idx"]+1]
        
        if turn["token_count"] <= remaining_tokens:
            # Đủ tokens - thêm toàn bộ turn
            selected_turn_messages = turn_messages + selected_turn_messages
            remaining_tokens -= turn["token_count"]
        else:
            # Turn quá lớn - thử extract essential messages (human + latest AI)
            essential_messages = _extract_human_and_ai_message(turn_messages)
            essential_tokens = count_tokens_approximately(essential_messages)
            
            if essential_tokens <= remaining_tokens:
                # Essential messages vừa đủ - thêm vào và tiếp tục với turns cũ hơn
                selected_turn_messages = essential_messages + selected_turn_messages
                remaining_tokens -= essential_tokens
            else:
                break
    
    # Nếu không có turn nào được chọn, giữ ít nhất turn cuối cùng (trimmed)
    if not selected_turn_messages and chat_turns:
        last_turn = chat_turns[-1]
        selected_turn_messages = _trim_tool_messages_in_turn_by_tokens(
            messages[last_turn["start_idx"]:last_turn["end_idx"]+1],
            remaining_tokens
        )
    
    # Kết hợp system messages và selected turns, giữ thứ tự gốc
    result.extend(selected_turn_messages)
    return _restore_message_order(result, messages)

def _get_latest_turn(
    messages: list[BaseMessage],
    keep_system_message: bool = True
) -> list[BaseMessage]:
    last_turn_messages: list[BaseMessage] = []
    for message in messages[::-1]:
        last_turn_messages.append(message)
        if isinstance(message, HumanMessage):
            break
    
    if (
        keep_system_message and
        messages and
        isinstance(messages[0], SystemMessage)
    ):
        last_turn_messages.append(messages[0])

    return last_turn_messages[::-1]
    
def _extract_human_and_ai_message(turn_messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Từ 1 turn, chỉ lấy HumanMessage đầu tiên và AIMessage without tool calls.
    
    Args:
        turn_messages: Danh sách messages trong 1 turn
        
    Returns:
        Danh sách chứa HumanMessage đầu tiên và AIMessage without tool calls.
    """
    essential = []
    for msg in turn_messages:
        if isinstance(msg, HumanMessage):
            essential.append(msg)
        elif isinstance(msg, AIMessage) and not msg.tool_calls:
            essential.append(msg)

    return essential

def _trim_tool_messages_in_turn_by_tokens(
    turn_messages: List[BaseMessage], 
    max_tokens: int
) -> List[BaseMessage]:
    """
    Trong 1 turn chat, bỏ bớt ToolMessages để fit vào max_tokens.
    ToolMessages được trim theo thứ tự từ đầu đến cuối (chronological order).
    """
    if not turn_messages:
        return turn_messages
    
    # Tách ToolMessages và non-ToolMessages
    tool_messages = []
    non_tool_messages = []
    
    for i, msg in enumerate(turn_messages):
        if isinstance(msg, ToolMessage):
            tool_messages.append((i, msg))
        else:
            non_tool_messages.append((i, msg))
    
    # Tính tokens của non-tool messages
    non_tool_tokens = count_tokens_approximately([message for _, message in non_tool_messages])
    
    # Nếu non-tool messages đã vượt quá giới hạn
    if non_tool_tokens > max_tokens:
        # Trường hợp cực đoan: chỉ giữ HumanMessage đầu tiên
        human_msg = next(
            (msg for _, msg in non_tool_messages if isinstance(msg, HumanMessage)), 
            None
        )
        if human_msg:
            return [human_msg]
        else:
            # Nếu không có HumanMessage, giữ message đầu tiên
            return turn_messages[:1] if turn_messages else []
    
    # Thêm ToolMessages theo thứ tự từ đầu đến cuối
    remaining_tokens = max_tokens - non_tool_tokens
    selected_tools = []
    
    # Giữ nguyên thứ tự original (từ đầu đến cuối)
    for original_idx, tool_msg in tool_messages:
        tool_tokens = count_tokens_approximately([tool_msg])
        if tool_tokens <= remaining_tokens:
            selected_tools.append((original_idx, tool_msg))
            remaining_tokens -= tool_tokens
        else:
            # Stop khi không còn đủ tokens
            break
    
    # Kết hợp và sắp xếp lại theo thứ tự ban đầu trong turn
    all_selected_with_idx = non_tool_messages + selected_tools
    all_selected_with_idx.sort(key=lambda x: x[0])  # Sort by original index
    
    return [msg for _, msg in all_selected_with_idx]

def _analyze_messages_by_tokens(
    messages: List[BaseMessage]
) -> Dict[str, Any]:
    """
    Phân tích cấu trúc messages để hiểu chat turns (token-based).
    
    Returns:
        {
            "system_messages": [indices],
            "chat_turns": [
                {
                    "start_idx": int,
                    "end_idx": int, 
                    "token_count": int,
                    "has_human": bool,
                    "tool_message_indices": [indices]
                }
            ],
            "total_tokens": int
        }
    """
    system_messages = []
    chat_turns = []
    current_turn = None
    
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            system_messages.append(i)
        elif isinstance(msg, HumanMessage):
            # Bắt đầu turn mới
            if current_turn is not None:
                chat_turns.append(current_turn)

            current_turn = {
                "start_idx": i,
                "end_idx": i,
                "token_count": count_tokens_approximately([msg]),
                "has_human": True,
                "tool_message_indices": []
            }
        elif current_turn is not None:
            # Tiếp tục turn hiện tại
            current_turn["end_idx"] = i
            msg_tokens = count_tokens_approximately([msg])
            current_turn["token_count"] += msg_tokens
            
            if isinstance(msg, ToolMessage):
                current_turn["tool_message_indices"].append(i)
    
    # Thêm turn cuối cùng
    if current_turn is not None:
        chat_turns.append(current_turn)
    total_tokens = count_tokens_approximately(messages)
    
    return {
        "system_messages": system_messages,
        "chat_turns": chat_turns,
        "total_tokens": total_tokens
    }

def count_tokens_approximately(
    messages,
    *,
    chars_per_token: float = 2.5,
    extra_tokens_per_message: float = 3.0,
    count_name: bool = True,
) -> int:
    """Approximate the total number of tokens in messages.

    The token count includes stringified message content, role, and (optionally) name.
    - For AI messages, the token count also includes stringified tool calls.
    - For tool messages, the token count also includes the tool call ID.

    Args:
        messages: Messages to count tokens for. Can be:
            - str: Single string to count
            - List[str]: List of strings to count
            - Iterable[MessageLikeRepresentation]: List of messages to count
        chars_per_token: Number of characters per token to use for the approximation.
            Default is 2.5 (one token corresponds to ~2.5 chars for common Vietnamese text).
            You can also specify float values for more fine-grained control.
            See more here: https://platform.openai.com/tokenizer
        extra_tokens_per_message: Number of extra tokens to add per message.
            Default is 3 (special tokens, including beginning/end of message).
            You can also specify float values for more fine-grained control.
            See more here:
            https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
        count_name: Whether to include message names in the count.
            Enabled by default.

    Returns:
        Approximate number of tokens in the messages.

    Note:
        This is a simple approximation that may not match the exact token count
        used by specific models. For accurate counts, use model-specific tokenizers.

    Warning:
        This function does not currently support counting image tokens.

    .. versionadded:: 0.3.46
    """
    if not messages:
        return extra_tokens_per_message

    # Handle string and list of strings
    if isinstance(messages, str):
        return math.ceil(len(messages) / chars_per_token + extra_tokens_per_message)
    
    if isinstance(messages, list) and messages and isinstance(messages[0], str):
        token_count = 0.0
        for text in messages:
            token_count += math.ceil(len(str(text)) / chars_per_token + extra_tokens_per_message)
        return math.ceil(token_count)
    
    # Handle MessageLikeRepresentation (original logic)
    token_count = 0.0
    for message in convert_to_messages(messages):
        message_chars = 0
        if isinstance(message.content, str):
            message_chars += len(message.content)

        # TODO: add support for approximate counting for image blocks
        else:
            content = repr(message.content)
            message_chars += len(content)

        if (
            isinstance(message, AIMessage)
            # exclude Anthropic format as tool calls are already included in the content
            and not isinstance(message.content, list)
            and message.tool_calls
        ):
            tool_calls_content = repr(message.tool_calls)
            message_chars += len(tool_calls_content)

        if isinstance(message, ToolMessage):
            message_chars += len(message.tool_call_id)

        role = _get_message_openai_role(message)
        message_chars += len(role)

        if message.name and count_name:
            message_chars += len(message.name)

        # NOTE: we"re rounding up per message to ensure that
        # individual message token counts add up to the total count
        # for a list of messages
        token_count += math.ceil(message_chars / chars_per_token)

        # add extra tokens per message
        token_count += extra_tokens_per_message

    # round up once more time in case extra_tokens_per_message is a float
    return math.ceil(token_count)

def _restore_message_order(
    selected_messages: List[BaseMessage], 
    original_messages: List[BaseMessage]
) -> List[BaseMessage]:
    """
    Sắp xếp lại selected messages theo thứ tự trong original messages.
    """
    # Tạo mapping từ message content và type đến index trong original
    original_map = {}
    for i, msg in enumerate(original_messages):
        key = _get_message_key(msg)
        if key not in original_map:
            original_map[key] = []
        original_map[key].append(i)
    
    # Sắp xếp selected messages theo thứ tự original
    message_with_order = []
    used_indices = set()
    
    for msg in selected_messages:
        key = _get_message_key(msg)
        if key in original_map:
            # Tìm index chưa được sử dụng
            for idx in original_map[key]:
                if idx not in used_indices:
                    message_with_order.append((idx, msg))
                    used_indices.add(idx)
                    break
    
    # Sort theo original index và return messages
    message_with_order.sort(key=lambda x: x[0])
    return [msg for _, msg in message_with_order]

def _get_message_key(msg: BaseMessage) -> Tuple[str, str]:
    """
    Tạo unique key cho message để map với original messages.
    """
    msg_type = type(msg).__name__
    content = str(msg.content) if hasattr(msg, "content") and msg.content else ""
    
    # Sử dụng hash của content để tránh key quá dài
    content_hash = str(hash(content))
    
    return (msg_type, content_hash)
