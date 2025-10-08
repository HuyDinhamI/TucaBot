from ..base import create_react_agent
from ..tools import get_template_document, generate_filled_document
from ..config import AgentConfig
from ..prompts.document import PROMPT_DOCUMENT

agent = create_react_agent(
    name="document_agent",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_DOCUMENT,
    tools=[get_template_document, generate_filled_document],
    dispatch_answer_event=True
)
