from typing import TypedDict, Sequence
from typing_extensions import Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.managed import IsLastStep, RemainingSteps

class AgentState(TypedDict):
    """The state of the agent."""
    
    messages: Annotated[Sequence[BaseMessage], add_messages]

    next_called_agent: str

    last_called_agent: str

    search_ids: set

    counter: dict

