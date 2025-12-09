import json
import re
import time
import requests
import logging
import filetype
import httpx
from uuid import uuid4
from pydantic import BaseModel
from urllib.parse import urlparse
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
from google.genai.types import GenerateContentResponse, HttpOptions
from openai.lib._parsing._completions import type_to_response_format_param

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
        base_url = kwargs.get("base_url")
        timeout = kwargs.get("timeout")
        headers = {
            "X-Provider-Code": "gemini",
            "X-API-Key": kwargs.get("api_key")
        }

        self.client = genai.Client(
            api_key=kwargs.get("api_key"),
            http_options=HttpOptions(
                base_url=base_url,
                headers=headers if base_url else None,
                timeout=timeout*1000 if timeout else None
            )
        )

    def with_structured_output(
        self, schema: Type[BaseModel]
    ) -> Optional[Union[Type[BaseModel], str]]:
        """Returns new lightweight wrapper"""
        try:
            return StructuredChatGoogleGenerativeAIWrapper(
                client=self,
                schema=schema
            )
        except Exception as e:
            logger.error("Error creating structured output wrapper: %s", e, exc_info=True)
            raise
    
    async def ainvoke(
        self,
        messages: Union[str, list[BaseMessage | dict]],
        tools: Optional[list] = None,
        temperature: Optional[float] = 0.0,
        config: Optional[RunnableConfig] = None,
        dispatch_answer_event: bool = True,
        dispatch_think_event: bool = True,
        stream: bool = True,
        **kwargs: Any
    ) -> Union[str, AIMessage]:
        st = time.time()
        logger.info(f"LLM start: {self.model}")

        ttft: float = None # time to first token
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
            gen_config["response_schema"] = kwargs.get("schema")
        if tools:
            tools = self.to_json_tools(tools)
            gen_config["tools"] = [{"function_declarations": tools}]

        gen_config = types.GenerateContentConfig(**gen_config)

        try:
            if stream:
                for chunk in self.client.models.generate_content_stream(
                    model=self.model,
                    contents=messages,
                    config=gen_config
                ):
                    if ttft is None:
                        ttft = time.time() - st
                        logger.info(f"First token latency: {ttft:.4f}s")
                    
                    await self._process_chunk(
                        chunk,
                        thought,
                        answer,
                        tool_calls,
                        config=config,
                        dispatch_answer_event=not kwargs.get("schema") and dispatch_answer_event,
                        dispatch_think_event=dispatch_think_event,
                        **kwargs
                    )

                et = time.time()
                ttlt = et - st  # time to last token
                logger.info(f"LLM end: {ttlt:.4f}s")

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
            else:
                response: GenerateContentResponse = self.client.models.generate_content(
                    model=self.model,
                    contents=messages,
                    config=gen_config
                )
                logger.info(f"LLM end: {time.time() - st:.2f}s")
                try:
                    content = response.candidates[0].content.parts[0].text
                except Exception as e:
                    content = ""
                return AIMessage(
                    content=content
                )
        
        except Exception as e:
            logger.error("Error in ainvoke: %s", e, exc_info=True)
            raise
    
    async def _process_chunk(
        self,
        chunk,
        thought: list[str],
        answer: list[str],
        tool_calls: list[dict],
        terminate_trigger: Optional[str] = None,
        config: Optional[RunnableConfig] = None,
        dispatch_answer_event: bool = True,
        dispatch_think_event: bool = True,
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
                    if dispatch_think_event:
                        await adispatch_custom_event(
                            name="on_think_stream",
                            data={
                                "title": kwargs.get("event_title") or "Suy luận",
                                "chunk": {
                                    "content": text
                                }
                            },
                            config=config
                        )
                    thought.append(text)

                else:
                    if dispatch_answer_event:
                        await adispatch_custom_event(
                            name=kwargs.get("event_name") or "on_answer_stream",
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
    
    def to_json_tools(self, tools: list[BaseTool | dict]):
        """Convert tools to the json format"""
        converted_tools = []
        for tool in tools:
            if isinstance(tool, BaseTool):
                state_args: dict = _get_state_args(tool)
                
                # Get JSON schema from Pydantic model if available
                properties = {}
                required = []
                
                if hasattr(tool, 'args_schema') and tool.args_schema:
                    try:
                        # Get the JSON schema from Pydantic model
                        json_schema = tool.args_schema.model_json_schema()
                        raw_properties = json_schema.get('properties', {})
                        
                        # Filter out state args and clean properties
                        for key, value in raw_properties.items():
                            if key not in state_args:
                                # Create clean property without Pydantic-specific fields
                                clean_prop = {}
                                
                                # Copy only standard JSON schema fields
                                if 'type' in value: 
                                    clean_prop['type'] = value['type']
                                if 'description' in value:
                                    clean_prop['description'] = value['description']
                                if 'default' in value:
                                    clean_prop['default'] = value['default']
                                if 'enum' in value:
                                    clean_prop['enum'] = value['enum']
                                if 'items' in value:
                                    clean_prop['items'] = value['items']
                                if 'format' in value:
                                    clean_prop['format'] = value['format']
                                    
                                properties[key] = clean_prop
                        
                        # Get required fields
                        required = [
                            k for k in json_schema.get('required', [])
                            if k not in state_args
                        ]
                        
                    except Exception as e:
                        logger.warning(f"Failed to get JSON schema for tool {tool.name}: {e}")
                        # Fallback:  try to use tool. args directly
                        properties = {}
                        
                elif hasattr(tool, 'args'):
                    # Fallback for tools without args_schema
                    for key, value in tool.args. items():
                        if key not in state_args:
                            properties[key] = {"type": "string"}
                
                tool_def = {
                    "name":  tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                    }
                }
                
                if required:
                    tool_def["parameters"]["required"] = required
                    
                converted_tools.append(tool_def)
                
            elif isinstance(tool, dict) and tool.get("function"):
                converted_tools.append(tool.get("function", {}))
            elif isinstance(tool, dict) and tool.get("name"):
                converted_tools.append(tool)

        return converted_tools

class StructuredChatGoogleGenerativeAIWrapper:
    def __init__(
        self, client: ChatGoogleGenerativeAI, schema: Type[BaseModel]
    ) -> NoReturn:
        self.client = client
        self.schema = schema
        self.json_schema = type_to_response_format_param(schema)
    
    async def ainvoke(
        self,
        messages: list[BaseMessage],
        max_retries: int = 2,
        **kwargs
    ) -> Union[str, Type[BaseModel]]:
        new_messages = messages.copy()
        new_messages.append(AIMessage(f"JSON schema: \n```\n{self.json_schema}\n``` \nI will strictly respond with a JSON object including keys corresponding to the properties defined in the JSON schema, using double quotes for both keys and string values."))
        
        for num_retry in range(max_retries):
            response = await self.client.ainvoke(
                messages=new_messages,
                schema=self.schema,
                **kwargs
            )
            
            if isinstance(response, Exception):
                raise response
            
            parsed_result, error_msg = parse_structured_response(response.content, self.schema)
            if parsed_result is not None:
                return parsed_result
            elif num_retry == max_retries - 1:
                logger.warning(f"Structured parsing failed after {max_retries} attempts: {error_msg}")
                return error_msg
            else:
                new_messages.append(AIMessage(content=error_msg))

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

                elif (
                    part.get("type") == "image" and
                    isinstance(part.get("file"), str)
                ):
                    file_bytes = download_image_to_bytes(part.get("file"))
                    if file_bytes:
                        mime_type = None
                        try:
                            kind = filetype.guess(file_bytes)
                            if kind:
                                mime_type = kind.mime
                        except Exception as e:
                            logger.error(f"Error guessing image type: {e}", exc_info=True)

                        inline_data = {"data": file_bytes, "mime_type": mime_type}
                        parts.append(types.Part(inline_data=inline_data))

                elif (
                    part.get("type") == "image" and
                    isinstance(part.get("file"), dict)
                ):
                    file_id = part.get("file", {}).get("file_id")
                    file_bytes = get_file_bytes(file_id)
                    if file_bytes:
                        mime_type = None
                        try:
                            kind = filetype.guess(file_bytes)
                            if kind:
                                mime_type = kind.mime
                        except Exception as e:
                            logger.error(f"Error guessing image type: {e}", exc_info=True)

                        inline_data = {"data": file_bytes, "mime_type": mime_type}
                        parts.append(types.Part(inline_data=inline_data))

                elif part.get("type") in ["pdf"]:
                    file_id = part.get("file", {}).get("file_id")
                    file_bytes = get_file_bytes(file_id)
                    if file_bytes:
                        inline_data = {"data": file_bytes, "mime_type": "application/pdf"}
                        parts.append(types.Part(inline_data=inline_data))

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

def get_file_bytes(
    file_id: str,
) -> bytes:
    """Get file bytes from MinIO API."""
    # return convert_image_to_bytes("misa.jpg", format="JPEG")
    try:
        response = requests.get(f"{get_bytes_api}/{type_doc}/{file_id}")
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        logger.error(f"Error fetching file bytes: {e}", exc_info=True)
        return b""
    
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

def download_image_to_bytes(image_url: str) -> bytes:
    """
    Download image từ URL public và trả về dưới dạng bytes
    
    Args:
        image_url (str): URL của ảnh cần download
        
    Returns:
        bytes: Raw bytes của ảnh, hoặc empty bytes nếu có lỗi
    """
    try:
        # Validate URL
        parsed_url = urlparse(image_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logger.error(f"URL không hợp lệ: {image_url}")
            return b""
        
        # Download image
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Get image bytes
        image_bytes = response.content
        
        logger.info(f"Đã download ảnh thành công từ URL: {image_url}")
        return image_bytes
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi khi download ảnh từ URL {image_url}: {str(e)}")
        return b""
    except Exception as e:
        logger.error(f"Lỗi không xác định khi xử lý ảnh từ URL {image_url}: {str(e)}")
        return b""
