import logging
from jinja2 import Template
from typing import TypedDict, Type, Literal, Optional, Union, Callable
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import (
    AIMessage,
    SystemMessage,
    ToolMessage,
    HumanMessage,
    BaseMessage
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ..utils.model_loader import ChatOpenAI, ChatGoogleGenerativeAI
from ..utils.messages_trimmer import trim_messages
from ..utils.messages_logger import log_prompt, clear_log_prompt
from ..config import AgentConfig
from ..state import AgentState
from .create_agent_call import create_agent_call

logger = logging.getLogger("uvicorn.error")

def create_called_agent_model(
    agents: dict[str, Union[CompiledStateGraph, Callable]]
) -> Type[BaseModel]:
    agent_choices = list(agents.keys())

    class CalledAgent(BaseModel):
        called_agent: Literal[tuple(agent_choices)] = Field(
            description="Tên agent được điều hướng tới."
        )
        explanation: str = Field(
            description="Giải thích ngắn gọn lý do điều hướng tới called_agent."
        )

    return CalledAgent

class Supervisor:
    def __init__(
        self,
        name: str,
        model: Union[ChatOpenAI | ChatGoogleGenerativeAI],
        prompt: str,
        agents: dict[str, Union[CompiledStateGraph, Callable]]
    ):
        self.name = name
        self.model = model
        self.prompt = prompt
        self.structured_output = create_called_agent_model(agents)
    
    async def __call__(self, state: AgentState, config: RunnableConfig):
        """Supervisor node that handles the handoff to other agents."""
        clear_log_prompt()
        
        messages = self._prepare_messages(state, config)
        response = await self.model.with_structured_output(self.structured_output).ainvoke(
            messages=messages,
            config=config
        )

        if AgentConfig.debug:
            log_prompt(messages, response, self.name)

        if isinstance(response, str):
            return {
                "messages": AIMessage(content=response, name=self.name),
                "next_called_agent": self.name
            }
        
        return {
            "next_called_agent": response.called_agent,
        }
    
    def _prepare_messages(
        self,
        state: AgentState,
        config: RunnableConfig
    ) -> list[BaseMessage]:
        prompt = Template(self.prompt).render(dict(
            **config.get("configurable", {})
        ))
        messages = [SystemMessage(prompt)]
        for message in state["messages"]:
            if (
                isinstance(message, HumanMessage) and
                isinstance(message.content, list) and
                len(message.content) == 1 and
                isinstance(message.content[0], dict) and
                message.content[0].get("type") == "text"
            ):
                messages.append(HumanMessage(content=message.content[0].get("text") or ""))
            else:
                messages.append(message)
        
        messages = trim_messages(messages, max_tokens=AgentConfig.max_input_tokens)
        return messages
    
class Edge(TypedDict):
    source: str
    dest: str

def create_supervisor_agent(
    name: str,
    model: Union[ChatOpenAI | ChatGoogleGenerativeAI],
    prompt: str,
    sub_agents: dict[str, Union[CompiledStateGraph, Callable]],
    edges: Optional[list[Edge]] = None,
    reset_state: Optional[dict[str, list[str]]] = None
) -> "CompiledStateGraph":
    # Init graph
    graph = StateGraph(AgentState)

    # Add nodes
    supervisor = Supervisor(
        name=name,
        model=model,
        prompt=prompt,
        agents=sub_agents
    )
    graph.add_node(name, supervisor)
    for agent_name, agent_callable in sub_agents.items():
        agent_call = create_agent_call(
            agent_name,
            agent_callable,
            reset_state.get(agent_name) if reset_state else None
        )
        graph.add_node(agent_name, agent_call)

    # Add edges
    def route_to_agents(state: AgentState):
        next_called_agent = state.get("next_called_agent")
        if next_called_agent:
            return next_called_agent
        return END

    graph.add_edge(START, name)
    graph.add_conditional_edges(name, route_to_agents)

    # If agent in a predefined edge, add edge
    # Otherwise, go back to the supervisor
    added_edges = set()
    for edge in edges:
        graph.add_edge(edge["source"], edge["dest"])
        added_edges.add(edge["source"])
                                            
    for agent_name in sub_agents:
        if agent_name not in added_edges:
            graph.add_edge(agent_name, name)

    # Compile graph
    graph = graph.compile(checkpointer=AgentConfig.memory)
    return graph
