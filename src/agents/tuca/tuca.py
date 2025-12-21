from langgraph.graph import END
from langchain_core.runnables import RunnableConfig

from ...base  import (
    create_handoff_tool,
    create_react_agent,
    create_network_agent
)
from ...tools import (
    search,
    lookup_administrative_division,
    check_online_admin_procedure
)
from ...config import AgentConfig
from ...state import AgentState
from ...prompts.tuca import *
from .custom.human_in_the_loop import create_human_in_the_loop

handoff_tools = {
    name: create_handoff_tool(name) for name in [
        "gather_user_information_agent",
        "search_agent",
        "answer_draft_agent",
        "answer_agent",
        "review_agent"
    ]
}

search_agent = create_react_agent(
    name="search_agent",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_SEARCH,
    tools=[search, lookup_administrative_division, check_online_admin_procedure],
    handoff_tools=[
        handoff_tools["gather_user_information_agent"],
        handoff_tools["answer_draft_agent"]
    ],
    fallback_handoff_tool=handoff_tools["gather_user_information_agent"],
    call_limit=2,
    notify_agent_call=True,
    ignore_content=True
)

gather_user_information_agent = create_human_in_the_loop(
    name="gather_user_information_agent",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_CLARIFY,
    fallback_handoff_tool=handoff_tools["answer_draft_agent"]
)

answer_draft_agent = create_react_agent(
    name="answer_draft_agent",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_ANSWER_DRAFT,
    handoff_tools=[
        handoff_tools["search_agent"],
        handoff_tools["review_agent"]
    ],
    fallback_handoff_tool=handoff_tools["review_agent"],
    dispatch_answer_event=False,
    call_limit=2
)

review_agent = create_react_agent(
    name="review_agent",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_REVIEW,
    handoff_tools=[
        handoff_tools["answer_draft_agent"],
        handoff_tools["answer_agent"],
        handoff_tools["search_agent"]
    ],
    fallback_handoff_tool=handoff_tools["answer_agent"],
    call_limit=2,
    notify_agent_call=True
)

answer_agent = create_react_agent(
    name="answer_agent",
    # model=AgentConfig.models["gpt-4.1-mini"],
    model=AgentConfig.models["gemini-2.5-flash"],
    prompt=PROMPT_ANSWER,
    dispatch_answer_event=True,
    call_limit=1
)

async def init(state: AgentState, config: RunnableConfig):
    state["counter"] = {}
    return {}

agent = create_network_agent(
    entry_agent_name="init",
    agents={
        "init": init,
        "gather_user_information_agent": gather_user_information_agent,
        "search_agent": search_agent,
        "answer_draft_agent": answer_draft_agent,
        "answer_agent": answer_agent,
        "review_agent": review_agent
    },
    handoff_tools=list(handoff_tools.values()),
    edges=[
        {"source": "init", "dest": "search_agent"},
        {"source": "answer_agent", "dest": END}
    ]
)
