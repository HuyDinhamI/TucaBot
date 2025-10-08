from langgraph.graph import END

from ..config import AgentConfig
from ..base import create_supervisor_agent
from ..prompts.supervisor import *
from .tuca import agent as tuca_agent
from .general import agent as general_agent
from .human_in_the_loop import agent as ask_user_agent
from .document import agent as document_agent

agent = create_supervisor_agent(
    name="router",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_ROUTING,
    sub_agents={
        "tuca_answer": tuca_agent,
        "general": general_agent,
        "document_answer": document_agent,
        "make_clear": ask_user_agent
    },
    edges=[
        {"source": "tuca_answer", "dest": END},
        {"source": "general", "dest": END},
        {"source": "document_answer", "dest": END},
        {"source": "make_clear", "dest": END}
    ],
    reset_state={}
)
