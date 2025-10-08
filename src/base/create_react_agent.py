import logging
import re
from uuid import uuid4
from jinja2 import Template
from typing import Optional, Literal, Union
from pydantic import BaseModel
from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import (
    AIMessage,
    SystemMessage,
    ToolMessage,
    HumanMessage,
    BaseMessage
)
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import END, START, StateGraph
from langchain_core.messages.tool import ToolCall
from langgraph.prebuilt import ToolNode

from ..config import AgentConfig
from ..state import AgentState
from ..utils.model_loader import ChatOpenAI, ChatGoogleGenerativeAI
from ..utils.messages_trimmer import trim_messages
from ..utils.messages_logger import log_prompt

logger = logging.getLogger("uvicorn.error")

class ReActAgent:
    def __init__(
        self,
        name: str,
        model: Union[ChatOpenAI | ChatGoogleGenerativeAI],
        prompt: str,
        tools: Optional[list[BaseTool]] = None,
        handoff_tools: Optional[list[BaseTool]] = None,
        fallback_handoff_tool: Optional[BaseTool] = None,
        structured_output: Optional[BaseModel] = None,
        dispatch_fields: Optional[list[str]] = None,
        dispatch_answer_event: Optional[bool] = False,
        dispatch_think_event: Optional[bool] = False,
        call_limit: Optional[int] = None,
        notify_agent_call: Optional[bool] = False,
        ignore_content: Optional[bool] = False,
        **kwargs
    ) -> None:
        self.name = name
        self.model = model
        self.prompt = prompt
        self.tool_names = [tool.name for tool in tools] if tools else []
        self.tools = ((tools or []) + (handoff_tools or []) or None)
        self.fallback_handoff_tool = fallback_handoff_tool
        self.structured_output = structured_output
        self.dispatch_fields = dispatch_fields
        self.dispatch_answer_event = dispatch_answer_event
        self.dispatch_think_event = dispatch_think_event
        self.call_limit = call_limit
        self.notify_agent_call = notify_agent_call
        self.ignore_content = ignore_content
    
    async def __call__(self, state: AgentState, config: RunnableConfig):
        try:
            logger.info(f"{self.name}: start")

            if self.notify_agent_call:
                await self._notify_agent_call(config)

            counter = state.get("counter") or {}
            num_calls = counter.get(self.name) or 0
            
            if self.name not in counter:
                counter[self.name] = 1
            else:
                counter[self.name] += 1

            if not self._is_valid_call(num_calls):
                if self.fallback_handoff_tool:
                    return {
                        "messages": AIMessage(
                            content="",
                            name=self.name,
                            tool_calls=[
                                ToolCall(
                                    name=self.fallback_handoff_tool.name,
                                    args={},
                                    id=str(uuid4())
                                )
                            ]
                        ),
                        "counter": counter
                    }
                
                return {
                    "messages": AIMessage(
                        content="system notify: agent call exceed limit",
                        name=self.name
                    ),
                    "counter": counter
                }

            if self.dispatch_answer_event:
                await adispatch_custom_event(
                    name="on_answer_event",
                    data={
                        "title": "",
                        "chunk": {
                            "content": "\n\n"
                        }
                    },
                    config=config
                )

            messages = self._prepare_messages(state, config)

            if self.structured_output is not None:
                response = await self.model.with_structured_output(self.structured_output).ainvoke(
                    messages=messages,
                    config=config
                )
                if AgentConfig.debug:
                    log_prompt(messages, response, self.name)

                if self.dispatch_answer_event and self.dispatch_fields:
                    for field in self.dispatch_fields:
                        if hasattr(response, field):
                            content = getattr(response, field)
                            await adispatch_custom_event(
                                name="on_answer_event",
                                data={
                                    "title": "",
                                    "chunk": {
                                        "content": str(content)
                                    }
                                },
                                config=config
                            )

                if self.fallback_handoff_tool:
                    tool_calls = [
                        ToolCall(
                            name=self.fallback_handoff_tool.name,
                            args={},
                            id=str(uuid4())
                        )
                    ]
                else:
                    tool_calls = []

                if self.ignore_content:
                    content = ""
                else:
                    content = str(response)

                return {
                    "messages": AIMessage(
                        content=content,
                        name=self.name,
                        tool_calls=tool_calls
                    ),
                    "counter": counter
                }
            
            else:
                response: AIMessage = await self.model.ainvoke(
                    messages=messages,
                    tools=self.tools,
                    config=config,
                    dispatch_answer_event=self.dispatch_answer_event,
                    dispatch_think_event=self.dispatch_think_event
                )
                if AgentConfig.debug:
                    log_prompt(messages, response, self.name)

                response.name = self.name

                if (
                    not (hasattr(response, "tool_calls") and response.tool_calls) and
                    self.fallback_handoff_tool
                ):
                    response.tool_calls = [
                        ToolCall(
                            name=self.fallback_handoff_tool.name,
                            args={},
                            id=str(uuid4())
                        )
                    ]
                
                elif (
                    self.notify_agent_call and
                    self.name == "search_agent" and
                    hasattr(response, "tool_calls") and
                    response.tool_calls and
                    response.tool_calls[0].get("name") in self.tool_names
                ):
                    args = response.tool_calls[0].get("args") or {}
                    queries = (args.get("background_search_queries") or []) + (args.get("in_depth_search_queries") or [])
                    if queries:
                        await adispatch_custom_event(
                            name="on_think_event",
                            data={
                                "title": "Thu thập và kiểm chứng",
                                "chunk": {
                                    "content": " \n\n".join(queries)
                                }
                            },
                            config=config
                        ) 

                if self.ignore_content:
                    response.content = ""
                return {
                    "messages": response,
                    "counter": counter
                }
        
        except Exception as e:
            return {
                "messages": AIMessage(
                    content=f"Đã có lỗi xảy ra khi thực hiện agent '{self.name}': {e}",
                    name=self.name,
                    tool_calls=[
                        ToolCall(
                            name=self.fallback_handoff_tool.name,
                            args={},
                            id=str(uuid4())
                        )
                    ]
                )
            }
        
    async def _notify_agent_call(
        self,
        config: RunnableConfig
    ):
        if self.name == "review_agent":
            await adispatch_custom_event(
                name="on_think_event",
                data={
                    "title": "Đánh giá và đề xuất",
                    "chunk": {
                        "content": ""
                    }
                },
                config=config
            )
        
    def _is_valid_call(
        self,
        num_calls: int = 0
    ) -> bool:
        if self.call_limit is not None:
            return num_calls < self.call_limit
        return True

    def _prepare_messages(
        self,
        state: AgentState,
        config: RunnableConfig
    ) -> list[BaseMessage]:
        configurable = self._format_configurable(config.get("configurable", {}))
        prompt = Template(self.prompt).render(dict(**configurable))

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
    
    def _format_configurable(self, configurable: dict) -> dict:
        if not isinstance(configurable, dict):
            return {}
        
        current_time = configurable.get("current_time")
        if isinstance(current_time, str) and current_time:
            configurable["current_time"] = current_time.split()[-1]
        return configurable
    
def create_react_agent(
    name: str,
    model: Union[ChatGoogleGenerativeAI | ChatOpenAI],
    prompt: str,
    tools: Optional[list[BaseTool]] = None,
    handoff_tools: Optional[list[BaseTool]] = None,
    fallback_handoff_tool: Optional[BaseTool] = None,
    structured_output: Optional[BaseModel] = None,
    dispatch_fields: Optional[list[str]] = None,
    dispatch_answer_event: Optional[bool] = False,
    dispatch_think_event: Optional[bool] = False,
    call_limit: Optional[int] = None,
    notify_agent_call: Optional[bool] = False,
    ignore_content: Optional[bool] = False,
) -> "CompiledStateGraph":
    assert not (tools and structured_output)

    # Init graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node(name, ReActAgent(
        name=name,
        model=model,
        prompt=prompt,
        tools=tools,
        handoff_tools=handoff_tools,
        fallback_handoff_tool=fallback_handoff_tool,
        structured_output=structured_output,
        dispatch_fields=dispatch_fields,
        dispatch_answer_event=dispatch_answer_event,
        dispatch_think_event=dispatch_think_event,
        call_limit=call_limit,
        notify_agent_call=notify_agent_call,
        ignore_content=ignore_content
    ))
    if tools:
        graph.add_node("tools", ToolNode(tools=tools))

    # Add edges
    graph.add_edge(START, name)
    if tools:
        tool_names: list[str] = [tool.name for tool in tools]
        graph.add_conditional_edges(
            name,
            lambda state: route_to_tools(
                state,
                tool_names=tool_names
            ),
            {
                "tools": "tools",
                "end": END
            }
        )
        graph.add_edge("tools", name)
    else:
        graph.add_edge(name, END)

    # Compile graph
    graph = graph.compile(checkpointer=AgentConfig.memory)
    return graph

def route_to_tools(
    state: AgentState,
    tool_names: list[str] = None
):
    ai_message = state["messages"][-1]
    if hasattr(ai_message, "tool_calls") and ai_message.tool_calls:
        tool_calls = filter_tool_calls(
            ai_message.tool_calls, 
            tool_names,
        )
        if tool_calls:
            state["messages"][-1].tool_calls = tool_calls
            return "tools"
    return "end"

def filter_tool_calls(
    tool_calls: list[dict],
    tool_names: list[str]
) -> list[dict]:
    filtered_tool_calls = []
    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        if tool_name in tool_names:
            filtered_tool_calls.append(tool_call)
    return filtered_tool_calls
