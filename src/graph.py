from langgraph.graph import START, END, StateGraph

from .state import AgentState
from .config import AgentConfig
from .agents.supervisor import agent as supervisor

graph = StateGraph(AgentState)

graph.add_node("supervisor", supervisor)

graph.add_edge(START, "supervisor")
graph.add_edge("supervisor", END)

graph = graph.compile(checkpointer=AgentConfig.memory)
