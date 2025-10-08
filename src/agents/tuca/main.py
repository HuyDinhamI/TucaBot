from langgraph.graph import END

from src.config import AgentConfig
from src.base  import create_supervisor_agent
from src.prompts.tuca import PROMPT_ROUTING
from .tuca import agent as tuca_agent

agent = create_supervisor_agent(
    name="tuca_router",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_ROUTING,
    sub_agents={
        "others": tuca_agent,
    },
    edges=[
        {"source": "others", "dest": END},
    ],
    reset_state={
        "others": ["counter"]
    }
)
