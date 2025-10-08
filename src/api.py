from typing import Dict, Any, List, Union, Literal, Optional, AsyncGenerator
import json
import time
import uuid
import base64
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from contextlib import asynccontextmanager, contextmanager
from fastapi import (
    FastAPI,
    Request,
    BackgroundTasks,
)
from pydantic import BaseModel, HttpUrl, Field
from langfuse.callback import CallbackHandler
from sse_starlette.sse import EventSourceResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder

from src.ai_core.api.chunks import router as chunks_router
from src.utils.read_file import get_file_content_from_file_id
from src.graph import graph
from src.settings import settings

logger = logging.getLogger("uvicorn.error")

# def connect_mongo():
#     client = MongoClient(
#         "mongodb://10.0.6.92:27017/?directConnection=true",
#         username=None,
#         password=None,
#         connect=False,
#     )
#     return client["MISAJSC-Langgraph"]

# mongo_db = connect_mongo()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting the app ...")
    yield
    logger.warning("Shutting down the app ...")

app = FastAPI(root_path=settings.API_CONF["root_path"], lifespan=lifespan)
app.include_router(chunks_router, tags=["Chunks Management"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", tags=["Health Check"])
@app.get("/healthz", tags=["Health Check"])
def get_heathz() -> Dict[str, str]:
    return {"status": "ok"}

class TextContent(BaseModel):
    type: Literal["text"]
    text: str

class FileData(BaseModel):
    filename: str = ""
    file_id: str
    file_content: Optional[str] = None

class FileContent(BaseModel):
    type: Literal["image", "docx", "pdf", "doc", "jpg", "png", "jpeg"]
    file: FileData

MessageContent = Union[TextContent, FileContent]

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: List[MessageContent]

    def __init__(self, **data):
        content = data.get("content")
        if isinstance(content, str):
            data["content"] = [TextContent(type="text", text=content)]
        super().__init__(**data)

class InputData(BaseModel):
    messages: List[Message]

class PayloadRequest(BaseModel):
    assistant_id: str = ""
    input: InputData = Field(default_factory=InputData)
    config: Dict[str, Any] = {}
    stream_mode: str = "events"
    stream_subgraphs: bool = False
    multitask_strategy: str = "enqueue"

def contain_file(input: dict) -> bool:
    """
    Check if the input data contains any file content.
    """
    for message in input.get("messages", []):
        for content in message.get("content", []):
            if isinstance(content, dict) and content.get("type") != "text":
                return True
    return False

def dump_message_content(input):
    new_messages = []
    for message in input.get("messages", []):
        # check if message.content is list
        if isinstance(message.get("content"), list):
            if (len(message["content"]) == 1 and message["content"][0].get("type") == "text"):
                message["content"] = message["content"][0].get("text") or ""
            else:
                message["content"] = json.dumps(message.get("content"), ensure_ascii=False)
        new_messages.append(message)
    input["messages"] = new_messages
    return input

def process_input(input: dict) -> tuple[dict, bool]:
    """
    Process the input:
        - Validate the input format, append a default text message if no content is present but files are included.
        - Read content from files if present.
        - Return the processed input and a success flag.
    If the input format is invalid or reading file content fails, return the original input and a failure flag.
    """
    success = True
    try:
        has_text: bool = False
        has_file: bool = False

        input: InputData = InputData.model_validate(input)
        for message in input.messages:
            for content in message.content:
                if (
                    isinstance(content, TextContent) and
                    content.text
                ):
                    has_text = True
                    if isinstance(content.text, str):
                        content.text = content.text.strip()

                elif (
                    isinstance(content, FileContent) and
                    content.file and
                    content.file.file_id
                ):
                    has_file = True
                    file_content = get_file_content_from_file_id(
                        file_id=content.file.file_id,
                        file_type=content.type,
                        file_name=content.file.filename,
                    )
                    if file_content:
                        content.file.file_content = file_content
                    else:
                        success = False
                        content.file.file_content = "Lỗi đọc file"
                        logger.error(f"Could not read content from file ID {content.file.file_id}")
        
        if not has_text and has_file:
            # Add default user message to the current user's message content
            default_text = "Tôi muốn hỏi về nội dung của các file đính kèm."
            for message in input.messages:
                if message.role == "user":
                    message.content.append(TextContent(type="text", text=default_text))
                    break

        return input.model_dump(), success
    
    except Exception as e:
        success = False
        logger.error(f"Invalid input format: {str(e)}")
        return input, success

def parse_start_event(event):
    if isinstance(event, dict):
        return {k: parse_start_event(v) for k, v in event.items()}
    elif isinstance(event, list):
        return [parse_start_event(item) for item in event]
    elif isinstance(event, tuple):
        return tuple(parse_start_event(item) for item in event)
    elif isinstance(event, str):
        return event
    else:
        try:
            return event.__dict__
        except:
            return event

def stripped_length(content: str) -> int:
    if isinstance(content, str):
        return len(content.strip())
    return 0

async def stream_from_agent(input, config, log_data, session_id):
    t1 = time.time()
    events = []
    run_idx = 0

    if contain_file(input):
        # Inform the user about reading file content
        # before processing the input
        event = {
            "event": "on_custom_event",
            "name": "on_think_event",
            "data": {
                "title": "Đọc file",
                "chunk": {
                    "content": "Đang đọc nội dung file",
                    "type": "AIMessageChunk",
                }
            },
        }
        yield json.dumps(jsonable_encoder(event), ensure_ascii=False)

    input, success = process_input(input)
    if contain_file(input) and not success:
        event = {
            "event": "on_custom_event",
            "name": "on_think_event",
            "data": {
                "title": "Đọc file",
                "chunk": {
                    "content": "\n\nLỗi đọc nội dung file",
                    "type": "AIMessageChunk",
                }
            },
        }
        yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
    
    # print("\nInput data:", input)

    answer_length = 0
    delay_answer_events = []
    thinking_lengths = {}
    delay_thinking_events = {}
    
    # dump file content to input
    input = dump_message_content(input)
    async for event in graph.astream_events(
        input,
        config=config,
        version="v2",
    ):
        t = time.time() - t1
        event = parse_start_event(event)
        
        # Xử lý các loại event
        if event["event"] == "on_custom_event":
            if event["name"] == "on_blocked_event":
                yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
                
            elif event["name"] == "on_passed_event":
                # yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
                continue
                
            elif event["name"] == "on_think_event":
                # Reset answer events
                answer_length = 0
                delay_answer_events = []

                # Handle thinking events
                content = event["data"].get("chunk", {}).get("content")
                title = event["data"].get("title", "")
                
                if title not in thinking_lengths:
                    thinking_lengths[title] = 0
                    delay_thinking_events[title] = []

                thinking_lengths = {k: 0 if k != title else v for k, v in thinking_lengths.items()}
                delay_thinking_events = {k: [] if k != title else v for k, v in delay_thinking_events.items()}

                thinking_lengths[title] += stripped_length(content)
                if thinking_lengths[title]:
                    if delay_thinking_events[title]:
                        for delay_event in delay_thinking_events[title]:
                            yield json.dumps(jsonable_encoder(delay_event), ensure_ascii=False)
                        delay_thinking_events[title] = []

                    if content:
                        yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
                else:
                    delay_thinking_events[title].append(event)

            elif event["name"] == "on_terminated_event":
                yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
                break

            elif event["name"] == "on_answer_event":
                thinking_lengths = {}
                delay_thinking_events = {}

                content = event["data"].get("chunk", {}).get("content")
                answer_length += stripped_length(content)
                if answer_length:
                    if content:
                        yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
                
            elif event["data"].get("chunk", {}).get("content"):
                yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
        
        elif event["event"] == "on_chat_model_stream":
            event["name"] = "on_answer_event"

            thinking_lengths = 0
            delay_thinking_events = {}

            content = event["data"].get("chunk", {}).get("content")
            answer_length += stripped_length(content)
            if answer_length:
                if content:
                    yield json.dumps(jsonable_encoder(event), ensure_ascii=False)
        
        # Theo dõi thông tin hiệu suất
        if event["event"] == "on_chat_model_start":
            log_data["runs"].append(
                {
                    "run": run_idx,
                    "start": t,
                }
            )
        elif event["event"] == "on_chat_model_stream":
            if not "ttft" in log_data["runs"][-1]:
                log_data["runs"][-1]["ttft"] = t
        elif event["event"] == "on_chat_model_end":
            log_data["runs"][-1]["stream"] = t - log_data["runs"][-1]["ttft"]
            log_data["runs"][-1]["end"] = t
            run_idx += 1

        events.append({"time": t, "event": event["event"]})
        
    log_data["events"] = events

@app.post(
    "/threads/{session_id}/runs/stream",
)
async def dispatch(
    session_id: str,
    request: Request,
    request_body: PayloadRequest,
    background_tasks: BackgroundTasks,
):
    if not session_id:
        session_id = str(uuid.uuid4())
        
    logger.info(f"Received request for session {session_id}:\n{request_body.__dict__}")
    input = jsonable_encoder(request_body.input)
    config = request_body.config

    log_data = {
        "session_id": session_id,
        "input": input.copy(),
        "config": config.copy(),
        "runs": [],
    }
    langfuse_handler = CallbackHandler(
        secret_key=settings.LANGFUSE_CONF["secret_key"],
        public_key=settings.LANGFUSE_CONF["public_key"],
        host=settings.LANGFUSE_CONF["host"],
        trace_name=settings.LANGFUSE_CONF["trace_name"],
        enabled=settings.LANGFUSE_CONF["enabled"],
        session_id=session_id,
        user_id=config.get("configurable", {}).get("user_id", ""),
        version=settings.LANGFUSE_CONF["version"],
    )
    if "configurable" not in config:
        config["configurable"] = {}

    if "thread_id" not in config["configurable"]:
        config["configurable"]["thread_id"] = session_id
        
    if "current_time" not in config["configurable"]:
        config["configurable"]["current_time"] = (
            datetime.now(timezone(timedelta(hours=7)))
            .strftime("%d/%m/%Y")
        )
    config["callbacks"] = [langfuse_handler]
    config["recursion_limit"] = 100
    
    return EventSourceResponse(
        stream_from_agent(input, config, log_data, session_id), media_type="text/plain"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8564,
    )
