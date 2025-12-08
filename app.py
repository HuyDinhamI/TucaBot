# -*- coding: utf-8 -*-
import streamlit as st
st.set_page_config(layout="wide", page_title="MAVAP")
import time
import asyncio
import logging
import io
import json
import os
from uuid import uuid4
from pymongo import MongoClient
from typing import AsyncGenerator, Any, Dict
# from langfuse.callback import CallbackHandler
from datetime import datetime, timezone, timedelta

# Tắt LangFuse error logging
logging.getLogger('langfuse').setLevel(logging.CRITICAL)
logging.getLogger('langfuse.callback').setLevel(logging.CRITICAL)
logging.getLogger('langfuse.callback.langchain').setLevel(logging.CRITICAL)

# Cấu hình logging để hiển thị trong Streamlit
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True
)

# Tạo stream handler đặc biệt để lưu logs vào bộ nhớ
log_stream = io.StringIO()
stream_handler = logging.StreamHandler(log_stream)
stream_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(formatter)

# Thêm handler vào root logger
root_logger = logging.getLogger()
root_logger.addHandler(stream_handler)

from src.settings import settings
from src.graph import graph
# from src.v1.graph import graph

def serialize_event_safely(event: Dict[str, Any]) -> Dict[str, Any]:
    """Safely serialize event data, handling LangChain objects and other non-serializable types"""
    try:
        def serialize_object(obj):
            if hasattr(obj, '__dict__'):
                # Handle LangChain message objects
                if hasattr(obj, 'content') and hasattr(obj, 'type'):
                    return {
                        'type': getattr(obj, 'type', str(type(obj).__name__)),
                        'content': str(getattr(obj, 'content', '')),
                        'name': getattr(obj, 'name', None),
                        'additional_kwargs': getattr(obj, 'additional_kwargs', {})
                    }
                # Handle other objects with __dict__
                return {k: serialize_object(v) for k, v in obj.__dict__.items()}
            elif isinstance(obj, (list, tuple)):
                return [serialize_object(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: serialize_object(v) for k, v in obj.items()}
            elif isinstance(obj, (str, int, float, bool, type(None))):
                return obj
            else:
                return str(obj)
        
        return serialize_object(event)
    except Exception as e:
        return {
            'error': f'Serialization failed: {str(e)}',
            'event_type': event.get('event', 'unknown'),
            'raw_str': str(event)
        }

def safe_log_event(event: Dict[str, Any], session_id: str):
    """Safely log event to file with error handling"""
    try:
        # Create logs directory if not exists
        os.makedirs('logs', exist_ok=True)
        
        # Serialize event safely
        serialized_event = serialize_event_safely(event)
        
        # Add metadata
        log_entry = {
            'timestamp': datetime.now(timezone(timedelta(hours=7))).isoformat(),
            'session_id': session_id,
            'event': serialized_event
        }
        
        # Log to session-specific file
        session_log_path = f'logs/session_{session_id}_events.jsonl'
        with open(session_log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        
        # Also log to general events file
        with open('logs/all_events.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            
    except Exception as e:
        # Fallback logging
        try:
            with open('logs/error_events.log', 'a', encoding='utf-8') as f:
                f.write(f"{datetime.now().isoformat()} - Failed to log event: {str(e)}\n")
                f.write(f"Event type: {event.get('event', 'unknown')}\n")
                f.write(f"Raw event: {str(event)[:500]}...\n\n")
        except:
            pass  # Silent fail if even error logging doesn't work

def init():
    session_id = str(uuid4())
    st.session_state.session_id = session_id
    
    # Cấu hình mặc định với agent_id cố định
    agent_id = "88886666-9999-4666-aaaa-88889999ffff"
    data = {
        'agent_id': agent_id,
        'thread_id': session_id,
        'response_markdown': True,
        "current_time": datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y")
    }
    
    st.session_state.config = {"configurable": data, "recursion_limit": 100}

st.title("Hỏi đáp với MAVAP Bot")

# Tạo expander cho logs và events
logs_expander = st.expander("Show Logs", expanded=False)
events_expander = st.expander("Show Events", expanded=False)

def show_recent_events():
    """Display recent events from the current session"""
    try:
        if "session_id" in st.session_state:
            session_log_path = f'logs/session_{st.session_state.session_id}_events.jsonl'
            if os.path.exists(session_log_path):
                with open(session_log_path, 'r', encoding='utf-8') as f:
                    events = []
                    for line in f:
                        try:
                            events.append(json.loads(line.strip()))
                        except:
                            continue
                    
                    if events:
                        # Show last 10 events
                        recent_events = events[-10:]
                        for event in recent_events:
                            timestamp = event.get('timestamp', 'Unknown')
                            event_type = event.get('event', {}).get('event', 'Unknown')
                            event_name = event.get('event', {}).get('name', '')
                            
                            st.write(f"**{timestamp}** - `{event_type}` {event_name}")
                            with st.expander(f"Event Details - {event_type}"):
                                st.json(event['event'])
                    else:
                        st.write("No events recorded for this session yet.")
            else:
                st.write("No events file found for this session.")
    except Exception as e:
        st.error(f"Error loading events: {str(e)}")

def clear_session():
    """Tạo phiên hội thoại hoàn toàn mới"""
    # Xóa tin nhắn hiện tại
    if "messages" in st.session_state:
        st.session_state.messages = []
    
    # Xóa logs
    log_stream.truncate(0)
    log_stream.seek(0)
    
    # Tạo session_id mới và khởi tạo lại config
    new_session_id = str(uuid4())
    st.session_state.session_id = new_session_id
    
    # Cập nhật config với session_id mới
    agent_id = "88886666-9999-4666-aaaa-88889999ffff"
    data = {
        'agent_id': agent_id,
        'thread_id': new_session_id,
        'response_markdown': True,
        "current_time": datetime.now(timezone(timedelta(hours=7))).strftime("%d/%m/%Y")
    }
    
    st.session_state.config = {"configurable": data, "recursion_limit": 100}
    
    # Hiển thị thông báo thành công
    st.success("✅ Đã tạo phiên hội thoại mới!")

st.button("Clear message", on_click=clear_session)

if "config" not in st.session_state:
    init()

if "messages" not in st.session_state:
    st.session_state.messages = []


async def process_events():
    start_time = time.time()
    start_think: bool = False
    
    async for event in graph.astream_events(inputs, config=st.session_state.config, version="v2"):
        # Log all events safely
        safe_log_event(event, st.session_state.session_id)
        # with open('events.txt', 'a', encoding='utf-8') as f:
        #     f.write(json.dumps(event, ensure_ascii=False) + '\n')
        
        if event["event"] == "on_custom_event":
            safe_log_event(event, st.session_state.session_id)
            if event["name"] == "on_blocked_event":
                # Trích xuất nội dung từ cấu trúc mới
                text = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text", "Nội dung bị chặn")
                yield f"🛑 {text}"

            elif event["name"] == "on_passed_event":
                # Trích xuất nội dung từ cấu trúc mới
                text = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text", "Nội dung đã được kiểm duyệt")
                yield f"✅ {text}"

            elif event["name"] == "on_think_event":
                # Trích xuất nội dung từ cấu trúc mới
                content = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text")
                if content:
                    if not start_think:
                        yield "\n\n**<think>**\n\n"
                        start_think = True

                    yield content

            elif event["name"] == "on_terminated_event":
                yield "Terminated"
                break
            
            # elif event["metadata"].get("langgraph_triggers") == ["branch:to:gather_user_information_agent"]:
            #     content = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text")
            #     if content:
            #         yield content
                    
            # # ✅ YIELD CHO ANSWER_AGENT  
            # elif event["metadata"].get("langgraph_triggers") == ["branch:to:answer_agent"]:
            #     content = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text")
            #     if content:
            #         yield content

            else:
                if start_think:
                    yield "\n\n**</think>**\n\n"
                    start_think = False

                if event["metadata"]. get("langgraph_node") == "ask_user":
                    # Trích xuất nội dung từ cấu trúc mới
                    content = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text")
                    if content:
                        yield content

                if event["metadata"]. get("langgraph_node") == "gather_user_information_agent":
                    # Trích xuất nội dung từ cấu trúc mới
                    content = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text")
                    if content:
                        yield content

                if event["metadata"]. get("langgraph_node") == "answer_agent":
                    # Trích xuất nội dung từ cấu trúc mới
                    content = event["data"].get("chunk", {}).get("content") if event["data"].get("chunk") else event["data"].get("text")
                    if content:
                        yield content
                    # pass
            
        # Bắt sự kiện trả lời từ LLM
        elif event["event"] == "on_chat_model_stream":
            answer_content = event["data"]["chunk"].content
            if answer_content:
                yield answer_content

def to_sync_generator(async_gen: AsyncGenerator):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        while True:
            try:
                yield loop.run_until_complete(anext(async_gen))
            except StopAsyncIteration:
                break
    finally:
        loop.close()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)

if prompt := st.chat_input("What is up?", max_chars=10000):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        inputs = {"messages": [{"role": "user", "content": [{"type": "text", "text": prompt.strip()}]}]}
        start_time = time.time()
        response = st.write_stream(to_sync_generator(process_events()))
        end_time = time.time() - start_time
        st.write(f"**Total time process**: {end_time}")
        id = uuid4().hex
        st.session_state.messages.append({"role": "assistant", "content": response, "id": id})
        
        # Hiển thị logs trong expander
        logs_content = log_stream.getvalue()
        if logs_content:
            with logs_expander:
                st.code(logs_content, language="text")
        
        # Hiển thị events trong expander
        with events_expander:
            show_recent_events()
