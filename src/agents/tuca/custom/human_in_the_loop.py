import logging
from uuid import uuid4
from jinja2 import Template
from typing import Optional, Union
from pydantic import BaseModel, Field
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

from src.config import AgentConfig
from src.state import AgentState
from src.utils.model_loader import ChatOpenAI, ChatGoogleGenerativeAI
from src.utils.messages_trimmer import trim_messages
from src.utils.messages_logger import log_prompt

logger = logging.getLogger("uvicorn.error")

class Result(BaseModel):
    need_gather_user_information: bool = Field(
        description="Dựa trên các kết quả tìm kiếm hiện tại được cung cấp, xác định xem có cần và có được phép thu thập thêm thông tin từ người dùng không."
    )
    question: Optional[str] = Field(
        default=None,
        description="Câu hỏi dành cho người dùng để thu thập thông tin từ người dùng (nếu cần và được phép). Câu hỏi này sẽ được gửi trực tiếp và nguyên văn tới người dùng."
    )
    num_generate_question: int = Field(
        description="Tổng số lần tạo câu hỏi để thu thập thông tin từ người dùng cho tới thời điểm hiện tại, tính trên một câu hỏi gốc của người dùng."
    )

class AskUserAgent:
    def __init__(
        self,
        name: str,
        model: Union[ChatOpenAI | ChatGoogleGenerativeAI],
        prompt: str,
        fallback_handoff_tool: Optional[BaseTool] = None,
        **kwargs
    ) -> None:
        self.name = name
        self.model = model
        self.prompt = prompt
        self.fallback_handoff_tool = fallback_handoff_tool
    
    async def __call__(self, state: AgentState, config: RunnableConfig):
        try:
            logger.info(f"{self.name}: start")

            messages = self._prepare_messages(state, config)
            response: Result = await self.model.with_structured_output(Result).ainvoke(
                messages=messages,
                config=config
            )
            if AgentConfig.debug:
                log_prompt(messages, response, self.name)

            if response.need_gather_user_information and response.question:
                await adispatch_custom_event(
                    name="on_answer_event",
                    data={
                        "title": "",
                        "chunk": {
                            "content": response.question
                        }
                    },
                    config=config
                )
                return {
                    "messages": AIMessage(
                        content=response.question,
                        name=self.name,
                        tool_calls=[]
                    )
                }

            tool_calls = []
            if self.fallback_handoff_tool:
                tool_calls = [
                    ToolCall(
                        name=self.fallback_handoff_tool.name,
                        args={},
                        id=str(uuid4())
                    )
                ]

            return {
                "messages": AIMessage(
                    content="",
                    name=self.name,
                    tool_calls=tool_calls
                )
            }
        
        except Exception as e:
            tool_calls = []
            if self.fallback_handoff_tool:
                tool_calls = [
                    ToolCall(
                        name=self.fallback_handoff_tool.name,
                        args={},
                        id=str(uuid4())
                    )
                ]
            return {
                "messages": AIMessage(
                    content=f"Đã có lỗi xảy ra khi thực hiện agent '{self.name}': {e}",
                    name=self.name,
                    tool_calls=tool_calls
                )
            }

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

def create_human_in_the_loop(
    name: str,
    model: Union[ChatOpenAI | ChatGoogleGenerativeAI],
    prompt: str,
    fallback_handoff_tool: Optional[BaseTool] = None,
    **kwargs
) -> "CompiledStateGraph":
    # Init graph
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node(name, AskUserAgent(
        name=name,
        model=model,
        prompt=prompt,
        fallback_handoff_tool=fallback_handoff_tool
    ))

    # Add edges
    graph.add_edge(START, name)
    graph.add_edge(name, END)

    # Compile graph
    graph = graph.compile(checkpointer=AgentConfig.memory)
    return graph