import os
from typing import List, Any
import logging

logger = logging.getLogger(__name__)

def log_prompt(
    messages: List[Any],
    response: Any,
    node_name: str
) -> None:
    """
    Ghi log messages trước khi gọi LLM và response sau khi nhận phản hồi
    
    Args:
        messages (List[Any]): Danh sách messages gửi tới LLM
        response (Any): Response từ LLM  
        node_name (str): Tên node/agent đang thực hiện
    
    Returns:
        None
    """
    with open(f"prompt_{node_name}.txt", "a", encoding="utf-8") as f:
        for message in messages:
            f.write(f"{message}\n\n")
        f.write(f"RESPONSE:\n{response}\n=====\n\n")
    # pass

def clear_log_prompt():
    for fn in os.listdir():
        if fn.startswith("prompt_") and fn.endswith(".txt"):
            os.remove(fn)
    # pass
