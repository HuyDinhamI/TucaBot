from typing import Optional, Union, Callable, Awaitable
from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

from ..state import AgentState

def create_agent_call(
    agent_name: str,
    agent_callable: Union[CompiledStateGraph, Callable[[AgentState, RunnableConfig], Awaitable[dict]]],
    reset_state: Optional[list[str]] = None
):
    """
    Create a call function for a specific agent.
    
    Args:
        agent: CompiledStateGraph instance or callable function
        agent_name: Name of the agent
        reset_state: list of fields in state to reset
        
    Returns:
        Async function that calls the agent
    """
    async def call_agent(state: AgentState, config: RunnableConfig) -> dict:
        try:
            # Reset state if required
            if reset_state:
                assert "messages" not in reset_state
                for field in reset_state:
                    state[field] = None
            
            # Handle based on agent type
            if isinstance(agent_callable, CompiledStateGraph):
                response: AgentState = await agent_callable.ainvoke(state, config)
            else:
                response: AgentState = await agent_callable(state, config)

            response = response if isinstance(response, dict) else {}

            return {
                **response,
                "last_called_agent": agent_name
            }
            
        except Exception as e:
            # Return error response
            return {
                "messages": AIMessage(content=f"Lỗi khi gọi agent {agent_name}: {str(e)}"),
                "last_called_agent": agent_name
            }
    
    # Set function name for debugging
    call_agent.__name__ = f"call_{agent_name}"
    return call_agent
