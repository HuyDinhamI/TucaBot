import re
import logging
from typing import Optional, Annotated, Union
from pydantic import BaseModel, Field
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, BaseTool
from langgraph.types import Command, Send

logger = logging.getLogger("uvicorn.error")

def create_handoff_tool(
    agent_name: str
) -> BaseTool:
    tool_name = f"handoff_to_{normalize_agent_name(agent_name)}"
    tool_desc = f"Handoff to agent '{agent_name}'."

    @tool(tool_name, description=tool_desc)
    def handoff_to_agent(
        message: Optional[str] = Field(
            default=None,
            description="Brief message for the handed-off agent about their task."
        ),
        state: Annotated[dict, InjectedState] = None
    ) -> dict:
        # return {}
        logger.info(f"Calling {agent_name}")
        return Command(
            goto=[Send(agent_name, {**state})]
        )
    handoff_to_agent.metadata = {"is_handoff_tool": True, "agent_name": agent_name}
    return handoff_to_agent

def normalize_agent_name(agent_name: str) -> str:
    """Normalize an agent name to be used inside the tool name."""
    return re.compile(r"\s+").sub("_", agent_name.strip()).lower()

if __name__ == "__main__":
    tool = create_handoff_tool("Example Agent")
    print(tool)