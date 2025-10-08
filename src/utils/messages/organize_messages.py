from copy import deepcopy
from collections.abc import Iterable
import math
from langchain_core.messages import (
    trim_messages,
    HumanMessage,
    AIMessage,
    ToolMessage
)
from langchain_core.messages.utils import (
    convert_to_messages,
    _get_message_openai_role,
    MessageLikeRepresentation
)

from src.state import AgentState

def organize_prompt_messages(
    state: AgentState,
    max_turns: int = 25,
    max_tokens: int = 1e5,
    **kwargs
) -> AgentState:
    new_state = deepcopy(state)
    new_state["messages"] = trim_messages(
        new_state["messages"],
        max_tokens=max_turns,
        strategy="last",
        token_counter=len,
        include_system=False,
        allow_partial=True,
        start_on="human"
    )
    new_state["messages"] = trim_messages(
        new_state["messages"],
        max_tokens=max_tokens,
        strategy="last",
        token_counter=count_tokens_approximately,
        include_system=False,
        allow_partial=True,
        start_on="human"
    )
    return new_state

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
    
    if isinstance(messages, list) and messages and all(isinstance(m, str) for m in messages):
        token_count = 0.0
        for text in messages:
            token_count += math.ceil(len(text) / chars_per_token + extra_tokens_per_message)
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

        # NOTE: we're rounding up per message to ensure that
        # individual message token counts add up to the total count
        # for a list of messages
        token_count += math.ceil(message_chars / chars_per_token)

        # add extra tokens per message
        token_count += extra_tokens_per_message

    # round up once more time in case extra_tokens_per_message is a float
    return math.ceil(token_count)
