from ..config import AgentConfig
from ..base  import create_react_agent
from ..prompts.supervisor import *

agent = create_react_agent(
    name="ask_user",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_ASK_USER,
    dispatch_answer_event=True
)
