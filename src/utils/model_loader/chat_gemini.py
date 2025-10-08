import json
import re
import time
import requests
import logging
import filetype
from uuid import uuid4
from pydantic import BaseModel
from typing import Optional, Union, Any, Type, NoReturn, Tuple, Sequence, List, Mapping
from langchain_google_genai._image_utils import ImageBytesLoader
from langchain_google_genai._common import GoogleGenerativeAIError
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    AIMessage,
    HumanMessage,
    ToolMessage
)
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig
from langchain_core.tools.base import BaseTool
from langchain_core.callbacks import adispatch_custom_event
from langgraph.prebuilt.tool_node import _get_state_args
from google import genai
from google.genai import types

from src.settings import settings
from src.utils.json_parser import parse_structured_response

# get_bytes_api = settings.MINIO_API_CONF["connection"]["get_bytes_api"]["host"]
# type_doc = settings.MINIO_API_CONF["connection"]["get_bytes_api"]["type"]

logger = logging.getLogger("uvicorn.error")

class ChatGoogleGenerativeAI:
    def __init__(
        self, api_key: str, model: str, **kwargs
    ):
        self.init_client(
            api_key=api_key,
            **kwargs
        )
        self.model = model
        self.kwargs = kwargs

    def init_client(self, **kwargs):
        self.client = genai.Client(
            api_key=kwargs.get("api_key"),
        )

    def with_structured_output(
        self, schema: Type[BaseModel]
    ) -> Optional[Type[BaseModel]]:
        """Returns new lightweight wrapper"""
        try:
            return StructuredChatGoogleGenerativeAIWrapper(
                client=self,
                schema=schema
            )
        except Exception as e:
            logger.error("Error creating structured output wrapper: %s", e, exc_info=True)
            return None
    
    async def ainvoke(
        self,
        messages: Union[str, list[BaseMessage | dict]],
        tools: Optional[list] = None,
        temperature: Optional[float] = 0.0,
        enable_thinking: bool = False,
        config: Optional[RunnableConfig] = None,
        dispatch_event: bool = True,
        **kwargs: Any
    ) -> AIMessage:
        # await adispatch_custom_event(
        #     name="on_chat_model_start",
        #     data={"input": {"messages": [messages]}},
        #     config=config
        # )

        try:
            st = time.time()
            logger.info(f"LLM start: {self.model}")

            ttft: float = None 
            thought: list[str] = []
            answer: list[str] = []
            tool_calls: list[dict] = []

            kwargs = self.kwargs | kwargs

            messages, system_instruction = self._convert_messages(messages)

            # Format messages to Gemini format
            if self.model == "gemini-2.5-pro":
                thinking_config=types.ThinkingConfig(include_thoughts=True)
            else:
                thinking_config=types.ThinkingConfig(thinking_budget=0)

            gen_config = {
                "temperature": temperature,
                "max_output_tokens": kwargs.get("max_tokens"),
                "thinking_config": thinking_config,  # Disabled due to JSON parsing bug
                "system_instruction": system_instruction,
            }
            if kwargs.get("schema"):
                gen_config["response_mime_type"] = "application/json"
                # Clean schema before passing to Gemini
                schema = kwargs.get("schema")
                if hasattr(schema, 'model_json_schema'):
                    raw_schema = schema.model_json_schema()
                    cleaned_schema = self._clean_schema_recursive(raw_schema)
                    gen_config["response_schema"] = cleaned_schema
                else:
                    gen_config["response_schema"] = schema
            if tools:
                tools = self.to_json_tools(tools)
                gen_config["tools"] = [{"function_declarations": tools}]

            gen_config = types.GenerateContentConfig(**gen_config)

            # async for chunk in await self.client.aio.models.generate_content_stream(
            #     model=self.model,
            #     contents=messages,
            #     config=gen_config
            # ):
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=messages,
                config=gen_config
            ):
                # Kiểm tra first token
                if ttft is None:
                    ttft = time.time() - st
                    logger.info(f"First token latency: {ttft:.2f}s")
                
                await self._process_chunk(
                    chunk,
                    thought,
                    answer,
                    tool_calls,
                    config=config,
                    dispatch_event=not kwargs.get("schema") and dispatch_event,
                    **kwargs
                )

            et = time.time()
            ttlt = et - st  # time to last token
            logger.info(f"LLM end: {ttlt:.2f}s")

            thought: str = "".join(thought)
            answer: str = "".join(answer)
            
            if tool_calls:
                tool_calls = self._format_tool_calls(tool_calls)

            elif thought:
                tool_calls = self._extract_tool_calls(thought)

            return AIMessage(
                content=answer,
                thought=thought,
                tool_calls=tool_calls,
                metadata=dict(
                    model_name=self.model,
                    ttft=ttft,
                    ttlt=ttlt
                )
            )
        
        except Exception as e:
            logger.error("Error in ainvoke: %s", e, exc_info=True)
            return AIMessage(
                content="",
                thought="",
                tool_calls=[],
                metadata=dict(
                    model_name=self.model,
                    error_message=str(e)
                )
            )
    
    async def _process_chunk(
        self,
        chunk,
        thought: list[str],
        answer: list[str],
        tool_calls: list[dict],
        terminate_trigger: Optional[str] = None,
        config: Optional[RunnableConfig] = None,
        dispatch_event: bool = True,
        **kwargs
    ):
        if (
            isinstance(chunk, str) and
            terminate_trigger is not None and
            chunk == terminate_trigger
        ):
            await adispatch_custom_event(
                name="on_terminated_event",
                data={},
                config=config
            )
            return
                
        if not hasattr(chunk, "candidates") or not chunk.candidates or not chunk.candidates[0].content:
            return

        parts: list[types.Part] = chunk.candidates[0].content.parts
        parts = parts if isinstance(parts, list) else []
        for part in parts:
            if part.function_call:
                chunk_tc: types.FunctionCall = part.function_call
                tool_calls.append({
                    "id": "",
                    "type": "function",
                    "function": {
                        "name": chunk_tc.name,
                        "arguments": json.dumps(chunk_tc.args, ensure_ascii=False) if chunk_tc.args else ""
                    }
                })

            if part.text:
                text = part.text or ""
                if part.thought:
                    if dispatch_event:
                        await adispatch_custom_event(
                            name="on_think_event",
                            data={
                                "title": "Suy luận",
                                "chunk": {
                                    "content": text
                                }
                            },
                            config=config
                        )
                    thought.append(text)

                else:
                    if dispatch_event:
                        await adispatch_custom_event(
                            name=kwargs.get("event_name") or "on_answer_event",
                            data={
                                "title": kwargs.get("event_title") or "",
                                "chunk": {
                                    "content": text
                                }
                            },
                            config=config
                        )
                    answer.append(text)
        return
    
    def _extract_tool_calls(self, text: str) -> list[ToolCall]:
        """Extract tool calls from the thought process."""
        pattern = r"<tool_call>(.*?)</tool_call>"
        matches = re.findall(pattern, text, re.DOTALL)

        tool_calls = []
        for match in matches:
            try:
                match = json.loads(match)
                tool_calls.append(ToolCall(
                    name=match["name"],
                    args=match["arguments"],
                    id=str(uuid4()),
                    type="tool_call"
                ))
            except Exception as e:
                logger.error(f"Error decoding tool call: {e}", exc_info=True)
                continue

        return tool_calls
    
    def _format_tool_calls(self, tool_calls: list[dict]) -> list[ToolCall]:
        """
        Format tool calls to the required format.
        Args:
            tool_calls (list[dict]): List of tool calls.
        Returns:
            list[dict]: Formatted tool calls.
        """
        formatted_tool_calls = []
        for tc in tool_calls:
            args = tc["function"]["arguments"]
            if isinstance(args, str) and args:
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    pass
            
            if not isinstance(args, dict):
                args = {}

            formatted_tool_calls.append(ToolCall(
                name=tc["function"]["name"],
                args=args,
                id=str(uuid4()),
                type="tool_call"
            ))

        return formatted_tool_calls
    
    def _convert_messages(
        self,
        messages: list[BaseMessage]
    ) -> Tuple[list[types.Content], Optional[str]]:
        gemini_contents = []
        system_instruction = None
        
        for message in messages:
            if isinstance(message, SystemMessage):
                parts = _convert_to_parts(message.content)
                if not system_instruction:
                    system_instruction = types.Content(parts=parts)
                elif hasattr(system_instruction, "parts") and system_instruction.parts:
                    system_instruction.parts.extend(parts)
            elif isinstance(message, HumanMessage):
                parts = _convert_to_parts(message.content)
                gemini_contents.append(
                    types.Content(
                        role="user",
                        parts=parts
                    )
                )
            elif isinstance(message, AIMessage):
                parts = _convert_to_parts(message.content)
                # Handle tool calls if present
                tool_calls = hasattr(message, "tool_calls") and message.tool_calls
                tool_calls = tool_calls if isinstance(tool_calls, list) else []
                for tool_call in tool_calls:
                    function_call = types.FunctionCall(
                        name=tool_call.get("name", ""),
                        args=tool_call.get("args", {}),
                        id=tool_call.get("id", ""),
                    )
                    parts.append(types.Part(function_call=function_call))
                
                if parts:
                    gemini_contents.append(
                        types.Content(
                            role="model",
                            parts=parts
                        )
                    )  
            elif isinstance(message, ToolMessage):
                name = message.name or message.additional_kwargs.get("name", "")
                id = message.tool_call_id or message.additional_kwargs.get("id", "")
                response: Any
                if not isinstance(message.content, str):
                    response = message.content
                else:
                    try:
                        response = json.loads(message.content)
                    except json.JSONDecodeError:
                        response = message.content

                parts = types.Part(
                    function_response=types.FunctionResponse(
                        id=id,
                        name=name,
                        response=(
                            {"output": response} if not isinstance(response, dict) else response
                        ),
                    )
                )
                gemini_contents.append(
                    types.Content(
                        role="model",
                        parts=[parts]
                    )
                )
        return gemini_contents, system_instruction
    
    @staticmethod
    def clean_schema(prop: dict) -> dict:
        """Loại bỏ các key không được Gemini hỗ trợ."""
        allowed_keys = {"type", "description", "enum", "items", "properties"}
        return {k: v for k, v in prop.items() if k in allowed_keys}
    
    def _clean_schema_recursive(self, schema: dict) -> dict:
        """Clean schema recursively, removing unsupported keys like additionalProperties."""
        if not isinstance(schema, dict):
            return schema
            
        # Remove unsupported keys
        unsupported_keys = ["additionalProperties", "$defs", "title"]
        cleaned = {k: v for k, v in schema.items() if k not in unsupported_keys}
        
        # Recursively clean nested structures
        if "properties" in cleaned:
            cleaned["properties"] = {
                k: self._clean_schema_recursive(v) for k, v in cleaned["properties"].items()
            }
        
        if "items" in cleaned:
            cleaned["items"] = self._clean_schema_recursive(cleaned["items"])
            
        if "anyOf" in cleaned:
            cleaned["anyOf"] = [self._clean_schema_recursive(item) for item in cleaned["anyOf"]]
            
        if "allOf" in cleaned:
            cleaned["allOf"] = [self._clean_schema_recursive(item) for item in cleaned["allOf"]]
            
        return cleaned

    def to_json_tools(self, tools: list[BaseTool | dict]):
        converted_tools = []
        for tool in tools:
            if isinstance(tool, BaseTool):
                state_args: dict = _get_state_args(tool)
                clean_props = {}
                for arg, spec in tool.args.items():
                    if arg in state_args:
                        continue
                    clean_props[arg] = ChatGoogleGenerativeAI.clean_schema(spec)
                converted_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": clean_props
                    }
                })
            elif isinstance(tool, dict) and tool.get("function"):
                converted_tools.append(tool["function"])
            elif isinstance(tool, dict) and tool.get("name"):
                converted_tools.append(tool)
        return converted_tools



class StructuredChatGoogleGenerativeAIWrapper:
    def __init__(
        self, client: ChatGoogleGenerativeAI, schema: Type[BaseModel]
    ) -> NoReturn:
        self.client = client
        self.schema = schema
    
    async def ainvoke(
        self, messages: list[BaseMessage], **kwargs
    ) -> Type[BaseModel]:
        try:
            response = await self.client.ainvoke(
                messages=messages,
                schema=self.schema,
                **kwargs
            )
            parsed_result, error_msg = parse_structured_response(response.content, self.schema)
            if parsed_result is not None:
                return parsed_result
            else:
                logger.warning(f"Structured parsing failed: {error_msg}")
                return self.schema()
                
        except Exception as e:
            logger.error("Error in ainvoke with structured output: %s", e, exc_info=True)
            return self.schema()

def _convert_to_parts(
    raw_content: Union[str, Sequence[Union[str, dict]]],
) -> List[types.Part]:
    """Converts a list of LangChain messages into a google parts."""
    parts = []
    content = [raw_content] if isinstance(raw_content, str) else raw_content
    image_loader = ImageBytesLoader()
    for part in content:
        if isinstance(part, str):
            parts.append(types.Part(text=part))

        elif isinstance(part, Mapping):
            # OpenAI Format
            if _is_openai_parts_format(part):
                if part["type"] == "text":
                    parts.append(types.Part(text=part["text"]))
                elif part["type"] == "image_url":
                    img_url = part["image_url"]
                    if isinstance(img_url, dict):
                        if "url" not in img_url:
                            raise ValueError(
                                f"Unrecognized message image format: {img_url}"
                            )
                        img_url = img_url["url"]
                    parts.append(image_loader.load_part(img_url))

                elif part["type"] == "media":
                    if "mime_type" not in part:
                        raise ValueError(f"Missing mime_type in media part: {part}")
                    mime_type = part["mime_type"]
                    media_part = types.Part()

                    if "data" in part:
                        media_part.inline_data = types.Blob(
                            data=part["data"], mime_type=mime_type
                        )
                    elif "file_uri" in part:
                        media_part.file_data = types.FileData(
                            file_uri=part["file_uri"], mime_type=mime_type
                        )
                    else:
                        raise ValueError(
                            f"Media part must have either data or file_uri: {part}"
                        )
                    if "video_metadata" in part:
                        metadata = types.VideoMetadata(part["video_metadata"])
                        media_part.video_metadata = metadata
                    parts.append(media_part)

                # elif part.get("type") == "image":
                #     file_id = part.get("file", {}).get("file_id")
                #     file_bytes = get_file_bytes(file_id)
                #     if file_bytes:
                #         mime_type = None
                #         try:
                #             kind = filetype.guess(file_bytes)
                #             if kind:
                #                 mime_type = kind.mime
                #         except Exception as e:
                #             logger.error(f"Error guessing image type: {e}", exc_info=True)

                #         inline_data = {"data": file_bytes, "mime_type": mime_type}
                #         parts.append(types.Part(inline_data=inline_data))

                # elif part.get("type") in ["pdf"]:
                #     file_id = part.get("file", {}).get("file_id")
                #     file_bytes = get_file_bytes(file_id)
                #     if file_bytes:
                #         inline_data = {"data": file_bytes, "mime_type": "application/pdf"}
                #         parts.append(types.Part(inline_data=inline_data))

                else:
                    raise ValueError(
                        f"Unrecognized message part type: {part['type']}. Only text, "
                        f"image_url, and media types are supported."
                    )
            else:
                # Yolo
                logger.warning(
                    "Unrecognized message part format. Assuming it's a text part."
                )
                parts.append(types.Part(text=str(part)))
        else:
            # TODO: Maybe some of Google's native stuff
            # would hit this branch.
            raise GoogleGenerativeAIError(
                "Gemini only supports text and inline_data parts."
            )
    return parts

def _is_openai_parts_format(part: dict) -> bool:
    return "type" in part

# def get_file_bytes(
#     file_id: str,
# ) -> bytes:
#     """Get file bytes from MinIO API."""
#     # return convert_image_to_bytes("misa.jpg", format="JPEG")
#     try:
#         response = requests.get(f"{get_bytes_api}/{type_doc}/{file_id}")
#         response.raise_for_status()
#         return response.content
#     except requests.RequestException as e:
#         logger.error(f"Error fetching file bytes: {e}", exc_info=True)
#         return b""
    
import base64
from pathlib import Path
from typing import Union
import requests
from PIL import Image
import io

def convert_image_to_bytes(
    image_source: Union[str, Path, bytes, Image.Image],
    format: str = "PNG"
) -> bytes:
    """
    Convert various image sources to bytes.
    
    Args:
        image_source: Can be:
            - File path (str or Path)
            - URL (str starting with http/https)
            - Base64 string (str starting with data:image)
            - Raw bytes
            - PIL Image object
        format: Output format (PNG, JPEG, etc.)
    
    Returns:
        bytes: Image data as bytes
    """
    try:
        # Handle PIL Image object
        if isinstance(image_source, Image.Image):
            buffer = io.BytesIO()
            image_source.save(buffer, format=format)
            return buffer.getvalue()
        
        # Handle bytes input
        if isinstance(image_source, bytes):
            return image_source
        
        # Handle string inputs
        if isinstance(image_source, (str, Path)):
            image_source = str(image_source)
            
            # Handle base64 data URLs
            if image_source.startswith("data:image"):
                # Extract base64 data after comma
                base64_data = image_source.split(",", 1)[1]
                return base64.b64decode(base64_data)
            
            # Handle URLs
            elif image_source.startswith(("http://", "https://")):
                response = requests.get(image_source, timeout=30)
                response.raise_for_status()
                return response.content
            
            # Handle local file paths
            else:
                file_path = Path(image_source)
                if file_path.exists() and file_path.is_file():
                    return file_path.read_bytes()
                else:
                    raise FileNotFoundError(f"Image file not found: {image_source}")
        
        raise ValueError(f"Unsupported image source type: {type(image_source)}")
        
    except Exception as e:
        return b""
