from pymongo import MongoClient
from langgraph.checkpoint.memory import MemorySaver

from src.memory.mongodb.saver import MongoDBSaver
from src.utils.model_loader import _get_model
from src.settings import settings

models = {
    "gpt-4.1-mini": _get_model(
        **settings.LLM_CONF["gpt-4.1-mini"]
    ),
    "gemini-2.5-flash": _get_model(
        **settings.LLM_CONF["gemini-2.5-flash"]
    ),
    "gemini-2.0-flash": _get_model(
        **settings.LLM_CONF["gemini-2.0-flash"]
    ),
    "gemini-2.5-pro": _get_model(
        **settings.LLM_CONF["gemini-2.5-pro"]
    )
}

class MemoryConfig:
    # client = MongoClient(
    #     settings.MONGO_CONF["connection"]["host"],
    #     username=settings.MONGO_CONF["connection"]["username"],
    #     password=settings.MONGO_CONF["connection"]["password"],
    # )
    # memory = MongoDBSaver(client, settings.MONGO_CONF["db_name"])
    memory = MemorySaver()

class SearchConfig:
    agent_id = settings.AGENT_CONF["agent_id"]
    top_docs = settings.SEARCH_CONF["vector_storage"]["top_k"]
    max_chars = settings.SEARCH_CONF["vector_storage"]["max_chars"]
    score_threshold = settings.SEARCH_CONF["vector_storage"]["score_threshold"]
    max_retries = settings.SEARCH_CONF["vector_storage"]["connection_params"]["max_retries"]

class AgentConfig:
    debug = True
    memory = MemoryConfig.memory
    max_input_tokens = 128_000
    models = models
