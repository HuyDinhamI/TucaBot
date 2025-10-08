from ..base  import create_react_agent
from ..tools import search_google, lookup_administrative_division
from ..config import AgentConfig
from ..prompts.general import *

agent = create_react_agent(
    name="general_agent",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_GENERAL,
    tools=[search_google, lookup_administrative_division],
    dispatch_answer_event=True
)
