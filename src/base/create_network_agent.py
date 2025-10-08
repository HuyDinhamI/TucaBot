from typing import Optional, TypedDict, Union, Callable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from ..config import AgentConfig
from ..state import AgentState
from .create_agent_call import create_agent_call

class Edge(TypedDict):
    source: str
    dest: str

def create_network_agent(
    entry_agent_name: str,
    agents: dict[str, Union[CompiledStateGraph, Callable]],
    handoff_tools: Optional[list[BaseTool]] = None,
    edges: Optional[list[Edge]] = None,
    reset_state: Optional[dict[str, list[str]]] = None
):
    # Init graph
    graph = StateGraph(AgentState)

    # Add nodes
    for agent_name, agent_callable in agents.items():
        agent_call = create_agent_call(
            agent_name,
            agent_callable,
            reset_state.get(agent_name) if reset_state else None
        )
        graph.add_node(agent_name, agent_call)
    
    if handoff_tools:
        graph.add_node("tools", ToolNode(tools=handoff_tools))

    # Add edges
    graph.add_edge(START, entry_agent_name)

    added_edges = set()
    for edge in edges:
        graph.add_edge(edge["source"], edge["dest"])
        added_edges.add(edge["source"])

    for agent_name in agents:
        if agent_name not in added_edges:
            graph.add_conditional_edges(agent_name, route_tools)

    if handoff_tools:
        graph.add_edge("tools", END)

    # Compile graph
    graph = graph.compile(checkpointer=AgentConfig.memory)
    return graph

def route_tools(state: AgentState):
    ai_message = state["messages"][-1]
    if (
        ai_message.name == state.get("last_called_agent") and
        hasattr(ai_message, "tool_calls") and
        ai_message.tool_calls
    ):
        return "tools"
    return END