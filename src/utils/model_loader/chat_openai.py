import json
import re
import time
import requests
import base64
import logging
from PIL import Image
from uuid import uuid4
from io import BytesIO
from pydantic import BaseModel
from urllib.parse import urlparse
from typing import Optional, Union, Any, Type, NoReturn, Tuple
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    AIMessage,
    HumanMessage,
    ToolMessage
)
from langchain_core.messages.tool import ToolCall
from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.tools.base import BaseTool
from langgraph.prebuilt.tool_node import _get_state_args
from openai import AsyncOpenAI
from openai._types import NOT_GIVEN
from openai.lib._parsing._completions import type_to_response_format_param

from src.utils.messages_trimmer.trim_messages import count_tokens_approximately
from src.utils.json_parser import parse_structured_response
from src.settings import settings

# get_image_url_api = settings.MINIO_API_CONF["connection"]["get_image_url_api"]["host"]
# type_doc = settings.MINIO_API_CONF["connection"]["get_image_url_api"]["type"]

logger = logging.getLogger("uvicorn.error")

class ChatOpenAI:
    def __init__(
        self, base_url: str, api_key: str, model: str, **kwargs
    ):
        self.init_client(
            base_url=base_url,
            api_key=api_key,
            **kwargs
        )
        self.model = model
        self.provider = kwargs.get("provider")
        self.kwargs = kwargs

    def init_client(self, **kwargs):
        self.aclient = AsyncOpenAI(
            base_url=kwargs.get("base_url"),
            api_key=kwargs.get("api_key"),
            max_retries=kwargs.get("max_retries", 3),
            timeout=kwargs.get("timeout"),
            default_headers=kwargs.get("default_headers"),
        )

    def with_structured_output(
        self, schema: Type[BaseModel]
    ) -> Optional[Union[Type[BaseModel], str]]:
        """Returns new lightweight wrapper"""
        try:
            return StructuredChatOpenAIWrapper(
                aclient=self,
                schema=schema
            )
        except Exception as e:
            logger.error("Error creating structured output wrapper: %s", e, exc_info=True)
            return e
        
    async def structured_output_ainvoke(
        self,
        messages: Union[str, list[BaseMessage | dict]],
        schema: Type[BaseModel],
        **kwargs
    ) -> Type[BaseModel]:
        try:
            st = time.time()
            kwargs = self.kwargs | kwargs
            messages = self._convert_messages(messages)
            # completion = await self.aclient.beta.chat.completions.parse(
            #     model=self.model,
            #     messages=messages,
            #     response_format=schema,
            #     temperature=kwargs.get("temperature") or 0.0,
            #     max_tokens=kwargs.get("max_tokens") or NOT_GIVEN
            # )
            # parsed = completion.choices[0].message.parsed
            json_format = type_to_response_format_param(schema)
            messages.append({
                "role": "assistant",
                "content": f"JSON schema: \n```\n{json_format}\n``` \nI will respond with a JSON object including keys corresponding to the properties defined in the JSON schema, using double quotes for both keys and string values."
            })

            if self.provider == "openai-compatible-server":
                extra_body = {
                    "chat_template_kwargs": {
                        "enable_thinking": False
                    },
                }
            else:
                extra_body = None
            response = await self.aclient.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                frequency_penalty=0.1,
                top_p=0.9,
                max_tokens=kwargs.get("max_tokens") or NOT_GIVEN,
                response_format={"type": "json_object"},
                extra_body=extra_body
            )
            parsed, error_message = parse_structured_response(response.choices[0].message.content, schema)

            et = time.time()
            ttlt = et - st
            logger.info(f"LLM end: {ttlt:.2f}s")
            if not parsed:
                print(response.choices[0].message.content)
                logger.error("Error in structured_output_ainvoke: %s", error_message, exc_info=True)
                return error_message
            return parsed
        
        except Exception as e:
            logger.error("Error in structured_output_ainvoke: %s", e, exc_info=True)
            return e
    
    async def ainvoke(
        self,
        messages: Union[str, list[BaseMessage | dict]],
        tools: Optional[list] = None,
        temperature: Optional[float] = 0.0,
        enable_thinking: bool = False,
        dispatch_answer_event: bool = True,
        dispatch_think_event: bool = True,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any
    ) -> Union[str, AIMessage]:
        await adispatch_custom_event(
            name="on_chat_model_start",
            data={"input": {"messages": [messages]}},
            config=config
        )

        kwargs = self.kwargs | kwargs
        messages = self._convert_messages(messages)
        input_tokens = count_tokens_approximately(messages)
        logger.info(f"LLM ainvoke: {input_tokens} tokens")        

        try:
            thought: str = ""
            answer: str = ""
            tool_calls: list[dict] = []

            first_token_received: bool = False
            ttft: float = None  # time to first token
            st = time.time()
            logger.info(f"LLM start: {self.model}")
            
            async for chunk in await self.aclient.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.to_json_tools(tools) if tools else NOT_GIVEN,
                temperature=temperature,
                max_tokens=kwargs.get("max_tokens") or NOT_GIVEN,
                stream=True,
                extra_body=kwargs.get("extra_body")
            ):
                # Kiểm tra first token
                if not first_token_received:
                    ttft = time.time() - st
                    logger.info(f"First token latency: {ttft:.2f}s")
                    first_token_received = True

                result = await self._process_chunk(
                    chunk,
                    thought,
                    answer,
                    tool_calls,
                    dispatch_answer_event=dispatch_answer_event,
                    dispatch_think_event=dispatch_think_event and enable_thinking,
                    config=config,
                    **kwargs
                )
                if result is None:
                    break
                thought, answer, tool_calls = result

            et = time.time()
            ttlt = et - st  # time to last token
            logger.info(f"LLM end: {ttlt:.2f}s")
            
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
                    input_tokens=input_tokens,
                    ttft=ttft,
                    ttlt=ttlt
                )
            )
        
        except Exception as e:
            logger.error("Error in ainvoke: %s", e, exc_info=True)
            return e
            # return AIMessage(
            #     content="",
            #     thought="",
            #     tool_calls=[],
            #     metadata=dict(
            #         model_name=self.model,
            #         input_tokens=input_tokens,
            #         error_message=str(e)
            #     )
            # )
    
    async def _process_chunk(
        self,
        chunk,
        thought: str,
        answer: str,
        tool_calls: list[dict],
        terminate_trigger: Optional[str] = None,
        dispatch_answer_event: Optional[bool] = True,
        dispatch_think_event: Optional[bool] = True,
        config: Optional[RunnableConfig] = None,
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

        delta = chunk.choices[0].delta

        if hasattr(delta, "tool_calls") and delta.tool_calls:
            chunk_tcs = delta.tool_calls
            for chunk_tc in chunk_tcs:
                function_name = chunk_tc.function.name
                if function_name and (not tool_calls or function_name != tool_calls[-1]["function"]["name"]):
                    tool_calls.append({
                        "id": "",
                        "type": "function",
                        "function": {"name": function_name, "arguments": ""}
                    })

                if chunk_tc.function.arguments:
                    tool_calls[-1]["function"]["arguments"] += chunk_tc.function.arguments

        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            if dispatch_think_event:
                await adispatch_custom_event(
                    name="on_think_event",
                    data={
                        "title": kwargs.get("event_title") or "Suy luận",
                        "chunk": {
                            "content": delta.reasoning_content
                        }
                    },
                    config=config
                )
            thought += delta.reasoning_content

        if hasattr(delta, "content") and delta.content:
            if dispatch_answer_event:
                await adispatch_custom_event(
                    name=kwargs.get("event_name") or "on_answer_event",
                    data={
                        "title": kwargs.get("event_title") or "",
                        "chunk": {
                            "content": delta.content
                        }
                    },
                    config=config
                )
            answer += delta.content

        return thought, answer, tool_calls
    
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
        messages: Union[str, list[BaseMessage | dict]]
    ) -> list[dict]:
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]
        return [self._base_message_to_dict(m) for m in messages]
    
    def _base_message_to_dict(
        self, message: BaseMessage, **kwargs
    ) -> dict:
        if not isinstance(message, BaseMessage):
            return message
        
        message_dict = {"content": self.format_message_content(message.content)}
        
        if isinstance(message, SystemMessage):
            message_dict["role"] = "system"
        
        elif isinstance(message, HumanMessage):
            message_dict["role"] = "user"
        
        elif isinstance(message, AIMessage):
            tool_calls = []
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False)
                        }
                    } for tc in message.tool_calls
                ]

            message_dict["role"] = "assistant"
            message_dict["tool_calls"] = tool_calls

        elif isinstance(message, ToolMessage):
            message_dict["role"] = "tool"
            message_dict["tool_call_id"] = message.tool_call_id

        return message_dict
    
    @staticmethod
    def format_message_content(content: Any) -> Any:
        """Format message content."""
        if not content or not isinstance(content, list):
            return content

        formatted_content = []
        for block in content:
            formatted_content.append(block)
            # # Remove unexpected block types
            # if (
            #     isinstance(block, dict)
            #     and "type" in block
            #     and block["type"] in ("tool_use", "thinking")
            # ):
            #     continue
            # # Anthropic image blocks
            # elif (
            #     isinstance(block, dict)
            #     and block.get("type") == "image"
            #     and (source := block.get("source"))
            #     and isinstance(source, dict)
            # ):
            #     if source.get("type") == "base64" and (
            #         (media_type := source.get("media_type"))
            #         and (data := source.get("data"))
            #     ):
            #         formatted_content.append(
            #             {
            #                 "type": "image_url",
            #                 "image_url": {"url": f"data:{media_type};base64,{data}"},
            #             }
            #         )
            #     elif source.get("type") == "url" and (url := source.get("url")):
            #         try:
            #             base64_string = fast_get_base64_from_image_url(url)
            #             formatted_content.append(
            #                 {
            #                     "type": "image_url",
            #                     "image_url": {"url": f"data:image/jpeg;base64,{base64_string}"}
            #                 }
            #             )
            #         except Exception as e:
            #             logger.warning(
            #                 f"Failed to convert image URL to base64: {url}, error: {e}")
            #             # Fallback to original URL
            #             formatted_content.append(
            #                 {"type": "image_url", "image_url": {"url": url}}
            #             )
            #     else:
            #         continue
            # elif (
            #     isinstance(block, dict)
            #     and block.get("type") == "image"
            # ):
            #     # Get link with file_id
            #     file_id = block.get("file", {}).get("file_id")
            #     image_url = f"{get_image_url_api}/{type_doc}/{file_id}"
            #     image_base64 = get_file_base64(image_url, file_type="image")
            #     if image_base64:
            #         formatted_content.append(
            #             {
            #                 "type": "image_url",
            #                 "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            #             }
            #         )
            #     else:
            #         formatted_content.append(
            #             {"type": "image_url", "image_url": {"url": image_url}}
            #         )
            # elif (
            #     isinstance(block, dict)
            #     and block.get("type") in ["pdf", "doc", "docx"]
            # ):
            #     # Call api get file content
            #     file_id = block.get("file", {}).get("file_id")
            #     file_url = f"{get_image_url_api}/{type_doc}/{file_id}"
            #     file_base64 = get_file_base64(file_url, file_type="file")
            #     if file_base64:
            #         formatted_content.append(
            #             {
            #                 "type": "file",
            #                 "file": {
            #                     "filename": file_id,
            #                     "file_data": f"data:application/pdf;base64,{file_base64}",
            #                 },
            #             }
            #         )
            # else:
            #     formatted_content.append(block)
        return formatted_content

    @staticmethod
    def to_json_tools(tools: list[BaseTool | dict]):
        """Convert tools to the json format"""
        converted_tools = []
        for tool in tools:
            if isinstance(tool, BaseTool):
                state_args: dict = _get_state_args(tool)
                converted_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                arg: v for arg, v in tool.args.items() if arg not in state_args
                            }
                        }
                    }
                })
            elif isinstance(tool, dict) and tool.get("function"):
                converted_tools.append(tool)
            elif isinstance(tool, dict) and tool.get("name"):
                converted_tools.append({
                    "type": "function",
                    "function": tool
                })

        return converted_tools

class StructuredChatOpenAIWrapper:
    def __init__(
        self, aclient: ChatOpenAI, schema: Type[BaseModel]
    ) -> NoReturn:
        self.aclient = aclient
        self.schema = schema
    
    async def ainvoke(
        self, messages: list[BaseMessage], **kwargs
    ) -> Type[BaseModel]:
        return await self.aclient.structured_output_ainvoke(
            messages=messages,
            schema=self.schema,
            **kwargs
        )
    
def get_file_base64(file_url: str, file_type: str) -> str:
    try:
        if file_type == "image":
            return fast_get_base64_from_image_url(file_url)
        else:
            file_bytes = requests.get(file_url).content
            file_base64 = base64.b64encode(file_bytes).decode("utf-8")
            return file_base64
    except Exception as e:
        logger.error(f"Failed to get file base64 from URL {file_url}: {e}")
        return ""

def fast_get_base64_from_image_url(image_url: str, max_size: int = 1024) -> str:
    """
    Download image from URL, resize if needed and encode to base64.

    Args:
        image_url: URL of the image to download
        max_size: Maximum size for width or height (default: 1024)

    Returns:
        Base64 encoded string of the processed image

    Raises:
        Exception: If unable to download or process the image
    """
    
    if isinstance(image_url, str) and not _is_url(image_url):
        return image_url  # If it"s not a URL, return as is

    try:
        # Download image
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()

        # Open image and get dimensions
        image = Image.open(BytesIO(response.content))
        width, height = image.size

        # Resize if necessary
        new_width, new_height = _resize_to_max(width, height, max_size)

        if new_width != width or new_height != height:
            # Resize image while maintaining aspect ratio
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (for RGBA, P mode images)
        if image.mode in ("RGBA", "LA", "P"):
            # Create white background
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "P":
                image = image.convert("RGBA")
            background.paste(image, mask=image.split()
                            [-1] if image.mode in ("RGBA", "LA") else None)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        # Save to BytesIO and encode to base64
        img_buffer = BytesIO()
        image.save(img_buffer, format="JPEG", quality=85, optimize=True)
        img_data = img_buffer.getvalue()

        # Encode to base64
        base64_string = base64.b64encode(img_data).decode("utf-8")

        return base64_string

    except requests.RequestException as e:
        logger.error(f"Failed to download image from URL {image_url}: {e}")
    except Exception as e:
        logger.error(f"Failed to process image from URL {image_url}: {e}")

def _resize_to_max(width: int, height: int, max_size: int) -> Tuple[int, int]:
    """Resize image to ensure both width and height <= max_size while maintaining aspect ratio."""
    if width <= max_size and height <= max_size:
        return width, height

    # Calculate scale factor
    scale = min(max_size / width, max_size / height)
    new_width = int(width * scale)
    new_height = int(height * scale)

    return new_width, new_height

def _is_url(s: str) -> bool:
    try:
        result = urlparse(s)
        return all([result.scheme, result.netloc])
    except Exception as e:
        logger.debug(f"Unable to parse URL: {e}")
        return False