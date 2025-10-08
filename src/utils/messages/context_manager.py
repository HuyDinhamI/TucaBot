from typing import List, Tuple, Union, Optional
import logging
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.utils.messages.organize_messages import count_tokens_approximately

logger = logging.getLogger(__name__)

def truncate_messages(
    messages: Union[List[BaseMessage], List[str], str],
    max_input_tokens: int,
    extra_tokens: int = 1000,
    max_turns: Optional[int] = None,
    strategy: str = "tokens"
) -> Union[List[BaseMessage], List[str], str]:
    """
    Truncate messages để phù hợp với max input tokens hoặc max turns
    
    Args:
        messages: Messages cần truncate, có thể là:
            - List[BaseMessage]: truncate theo turn logic hoặc tokens
            - List[str]: truncate từ latest về trước (simple)
            - str: bỏ qua, trả về nguyên
        max_input_tokens: Số input tokens tối đa cho phép
        extra_tokens: Số tokens dự phòng để đảm bảo không vượt quá giới hạn (mặc định 1000)
        max_turns: Số turns tối đa cho phép (chỉ áp dụng với strategy="turns")
        strategy: Chiến lược truncate - "tokens" hoặc "turns" (mặc định "tokens")
        
    Returns:
        Messages đã được truncate với cùng định dạng input
        
    Logic:
        - strategy="tokens": Truncate theo max_input_tokens (logic hiện tại)
        - strategy="turns": Truncate theo max_turns (chỉ với List[BaseMessage])
        - List[str]: Luôn truncate từ latest về trước, không quan tâm turn
        - str: Bỏ qua truncation
    """
    # Validation cho strategy="turns"
    if strategy == "turns":
        if max_turns is None:
            raise ValueError("max_turns không được None khi strategy='turns'")
        if not (isinstance(messages, list) and messages and all(isinstance(m, BaseMessage) for m in messages)):
            logger.warning("strategy='turns' chỉ áp dụng cho List[BaseMessage], fallback về strategy='tokens'")
            strategy = "tokens"
    
    # Case 1: Single string - bỏ qua
    if isinstance(messages, str):
        return messages
    
    # Case 2: List of strings - simple truncation from latest
    elif isinstance(messages, list) and messages and all(isinstance(m, str) for m in messages):
        return _truncate_string_list(messages, max_input_tokens, extra_tokens)
    
    # Case 3: List of BaseMessage - existing turn-based logic
    elif isinstance(messages, list) and messages and all(isinstance(m, BaseMessage) for m in messages):
        if strategy == "turns":
            return _truncate_base_messages_by_turns(messages, max_turns)
        else:
            return _truncate_base_messages_by_tokens(messages, max_input_tokens, extra_tokens)
    
    # Case 4: Empty list
    elif isinstance(messages, list) and not messages:
        return messages
    
    else:
        raise ValueError(f"Unsupported message type: {type(messages)}")

def _truncate_string_list(strings: List[str], max_input_tokens: int, extra_tokens: int) -> List[str]:
    """
    Truncate danh sách string từ latest về trước
    
    Args:
        strings: Danh sách string cần truncate
        max_input_tokens: Số input tokens tối đa cho phép
        extra_tokens: Số tokens dự phòng
        
    Returns:
        Danh sách string đã được truncate
    """
    if not strings:
        return strings
    
    logger.info("Truncating string list to fit within max input tokens: %d", max_input_tokens)
    
    # Đảm bảo có đủ tokens cho xử lý
    # Nếu extra_tokens quá lớn, giảm nó xuống để vẫn có thể xử lý
    effective_extra_tokens = min(extra_tokens, max_input_tokens // 2)
    available_tokens = max_input_tokens - effective_extra_tokens
    
    if available_tokens <= 0:
        logger.warning(f"Not enough tokens after subtracting extra_tokens: {max_input_tokens} - {effective_extra_tokens} = {available_tokens}")
        return []
    
    selected = []
    current_tokens = 0.0
    
    # Duyệt từ cuối về đầu
    for s in reversed(strings):
        # Ước tính số tokens của string (2.5 chars per token + 3 extra per message)
        s_tokens = len(s) / 2.5 + 3.0
        
        logger.debug(f"String: '{s[:20]}...', length: {len(s)}, estimated tokens: {s_tokens:.1f}")
        
        if current_tokens + s_tokens <= available_tokens:
            selected.insert(0, s)  # insert at beginning to maintain order
            current_tokens += s_tokens
            logger.debug(f"Added string, current total tokens: {current_tokens:.1f}")
        else:
            logger.debug(f"Cannot add string, would exceed limit: {current_tokens + s_tokens:.1f} > {available_tokens}")
            break
    
    logger.info(f"Selected {len(selected)} strings with total estimated tokens: {current_tokens:.1f}")
    
    return selected

def _truncate_base_messages_by_turns(
    messages: List[BaseMessage],
    max_turns: int
) -> List[BaseMessage]:
    """
    Truncate messages theo số lượng turns tối đa
    
    Args:
        messages: Danh sách messages cần truncate
        max_turns: Số turns tối đa cho phép
        
    Returns:
        Danh sách messages đã được truncate theo số turns
        
    Logic:
        - Luôn giữ lại SystemMessage (không tính vào max_turns)
        - Giữ lại max_turns conversation turns gần nhất
        - Mỗi turn bắt đầu bằng HumanMessage
        - Giữ nguyên tính toàn vẹn của từng turn
    """
    if not messages or max_turns <= 0:
        # Chỉ trả về SystemMessage nếu có
        return [msg for msg in messages if isinstance(msg, SystemMessage)]
    
    logger.info("Truncating messages to fit within max turns: %d", max_turns)
    
    # Tách system messages và conversation messages
    system_messages = []
    conversation_messages = []
    
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_messages.append(msg)
        else:
            conversation_messages.append(msg)
    
    # Xác định các turn trong conversation
    turns = _identify_turns(conversation_messages)
    
    if not turns:
        # Không có turn nào, chỉ trả về system messages
        logger.info("No turns found, returning only system messages")
        return system_messages
    
    # Giữ lại max_turns turns gần nhất
    selected_turns = turns[-max_turns:] if len(turns) > max_turns else turns
    
    # Lấy messages tương ứng với selected turns
    if selected_turns:
        start_idx = selected_turns[0][0]  # Bắt đầu từ turn đầu tiên được chọn
        end_idx = selected_turns[-1][1]   # Kết thúc tại turn cuối cùng được chọn
        selected_conversation = conversation_messages[start_idx:end_idx + 1]
    else:
        selected_conversation = []
    
    # Kết hợp system messages và selected conversation
    result = system_messages + selected_conversation
    
    logger.info(f"Selected {len(selected_turns)}/{len(turns)} turns")
    
    return result

def _truncate_base_messages_by_tokens(
    messages: List[BaseMessage],
    max_input_tokens: int,
    extra_tokens: int = 1000
) -> List[BaseMessage]:
    """
    Truncate messages theo tokens để phù hợp với max input tokens
    
    Args:
        messages: Danh sách messages cần truncate
        max_input_tokens: Số input tokens tối đa cho phép
        extra_tokens: Số tokens dự phòng để đảm bảo không vượt quá giới hạn (mặc định 1000)
        
    Returns:
        Danh sách messages đã được truncate theo tokens
        
    Logic:
        - Một turn bắt buộc phải bắt đầu từ HumanMessage
        - Giữ nguyên vẹn từng turn (không cắt giữa turn)
        - Ưu tiên giữ lại các turn gần đây nhất (liền mạch từ cuối lên)
        - Luôn giữ lại SystemMessage
        - Dừng ngay khi gặp turn làm vượt quá max tokens (không nhảy cóc)
    """
    if not messages:
        return messages
    
    logger.info("Truncating messages to fit within max input tokens: %d", max_input_tokens)
    
    max_input_tokens -= extra_tokens
    
    # Tách system messages và conversation messages
    system_messages = []
    conversation_messages = []
    
    for msg in messages:
        if isinstance(msg, SystemMessage):
            system_messages.append(msg)
        else:
            conversation_messages.append(msg)
    
    # Tính input tokens của system messages
    system_tokens = count_tokens_approximately(system_messages) if system_messages else 0
    remaining_input_tokens = max_input_tokens - system_tokens
    
    if remaining_input_tokens <= 0:
        # Nếu system messages đã vượt quá giới hạn input tokens
        return system_messages
    
    # Xác định các turn trong conversation
    turns = _identify_turns(conversation_messages)
    
    if not turns:
        # Không có turn nào, trả về system messages
        return system_messages
    
    # Chọn turn từ cuối lên đầu để fit vào remaining input tokens (liền mạch)
    selected_messages = []
    current_input_tokens = 0
    selected_turns = 0
    
    # Duyệt từ turn cuối cùng ngược lên đầu
    for turn_start, turn_end in reversed(turns):
        turn_tokens = _calculate_turn_tokens(conversation_messages, turn_start, turn_end)
        
        # Kiểm tra xem có thể thêm turn này không
        if current_input_tokens + turn_tokens <= remaining_input_tokens:
            # Thêm turn này vào đầu danh sách
            turn_messages = conversation_messages[turn_start:turn_end + 1]
            selected_messages = turn_messages + selected_messages
            current_input_tokens += turn_tokens
            selected_turns += 1
            logger.debug(f"Added turn {selected_turns}, tokens: {turn_tokens}, total: {current_input_tokens}")
        else:
            # Không thể thêm turn này, dừng luôn (đảm bảo liền mạch)
            logger.debug(f"Cannot add turn, would exceed limit: {current_input_tokens + turn_tokens} > {remaining_input_tokens}")
            break
    
    # Kết hợp system messages và selected conversation messages
    result = system_messages + selected_messages
    total_tokens = system_tokens + current_input_tokens
    
    logger.info(f"Selected {selected_turns}/{len(turns)} turns with total estimated tokens: {total_tokens:.1f}")
    
    return result

def _identify_turns(messages: List[BaseMessage]) -> List[Tuple[int, int]]:
    """
    Xác định các turn trong messages
    Mỗi turn bắt đầu từ HumanMessage và bao gồm các message liên quan tiếp theo
    
    Returns:
        List của (start_idx, end_idx) cho mỗi turn
    """
    turns = []
    current_turn_start = None
    
    for i, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            # Kết thúc turn trước đó (nếu có)
            if current_turn_start is not None:
                turns.append((current_turn_start, i - 1))
            
            # Bắt đầu turn mới
            current_turn_start = i
    
    # Kết thúc turn cuối cùng
    if current_turn_start is not None:
        turns.append((current_turn_start, len(messages) - 1))
    
    return turns

def _calculate_turn_tokens(messages: List[BaseMessage], start_idx: int, end_idx: int) -> int:
    """Tính số tokens của một turn"""
    turn_messages = messages[start_idx:end_idx + 1]
    return count_tokens_approximately(turn_messages)

def get_messages_token_count(messages: List[BaseMessage]) -> int:
    """Đếm tổng số input tokens trong messages"""
    return count_tokens_approximately(messages)

def check_messages_fit(
    messages: List[BaseMessage],
    max_input_tokens: int,
    max_output_tokens: int
) -> dict:
    """
    Kiểm tra xem messages có vừa với max input tokens không
    
    Returns:
        Dict chứa thông tin:
        - fits: bool - có vừa không
        - current_input_tokens: int - số tokens hiện tại
        - max_input_tokens: int - số tokens tối đa cho input
        - max_output_tokens: int - số tokens tối đa cho output
        - overflow_tokens: int - số tokens vượt quá (nếu có)
    """
    current_input_tokens = get_messages_token_count(messages)
    fits = current_input_tokens <= max_input_tokens
    overflow_tokens = max(0, current_input_tokens - max_input_tokens)
    
    return {
        "fits": fits,
        "current_input_tokens": current_input_tokens,
        "max_input_tokens": max_input_tokens,
        "max_output_tokens": max_output_tokens,
        "overflow_tokens": overflow_tokens
    }
